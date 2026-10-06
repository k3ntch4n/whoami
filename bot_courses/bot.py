"""Bot Telegram de liste de courses, piloté par Claude.

Écris en langage naturel ("de quoi faire des crêpes pour 6", "retire le lait"),
Claude met la liste à jour. /liste affiche la liste avec un bouton par article
pour le cocher au magasin.
"""

import asyncio
import html
import json
import logging
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot_courses")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
MODELE = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
FICHIER = Path(os.environ.get("LISTES_FILE", Path(__file__).with_name("listes.json")))
AUTORISES = {int(x) for x in os.environ.get("ALLOWED_USERS", "").replace(" ", "").split(",") if x}

claude = anthropic.AsyncAnthropic()
verrou = asyncio.Lock()

RAYONS = [
    "fruits et légumes", "boucherie / poisson", "frais", "boulangerie",
    "épicerie", "boissons", "surgelés", "hygiène", "entretien", "divers",
]


# --- Stockage : une liste par conversation (marche aussi dans un groupe familial) ---

def charger_tout() -> dict:
    if FICHIER.exists():
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    return {}


def sauver_tout(data: dict) -> None:
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(FICHIER)


def liste_de(data: dict, chat_id: int) -> dict:
    return data.setdefault(str(chat_id), {"prochain_id": 1, "articles": {}})


def trouver(liste: dict, nom: str) -> str | None:
    nom = nom.strip().lower()
    for id_, art in liste["articles"].items():
        if art["nom"].lower() == nom:
            return id_
    return None


# --- Outils donnés à Claude ---

OUTILS = [
    {
        "name": "ajouter",
        "description": "Ajoute un ou plusieurs articles. Si l'article existe déjà, sa quantité est remplacée.",
        "input_schema": {
            "type": "object",
            "properties": {
                "articles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "nom": {"type": "string", "description": "Nom court au singulier, ex: 'tomate'"},
                            "quantite": {"type": "string", "description": "ex: '4', '500 g', '1 L'"},
                            "rayon": {"type": "string", "enum": RAYONS},
                        },
                        "required": ["nom", "rayon"],
                    },
                }
            },
            "required": ["articles"],
        },
    },
    {
        "name": "retirer",
        "description": "Retire des articles de la liste (par leur nom exact dans la liste).",
        "input_schema": {
            "type": "object",
            "properties": {"noms": {"type": "array", "items": {"type": "string"}}},
            "required": ["noms"],
        },
    },
    {
        "name": "vider",
        "description": "Vide entièrement la liste. Seulement si l'utilisateur le demande explicitement.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def executer(liste: dict, nom: str, entree: dict) -> str:
    if nom == "ajouter":
        for art in entree["articles"]:
            id_ = trouver(liste, art["nom"])
            if id_ is None:
                id_ = str(liste["prochain_id"])
                liste["prochain_id"] += 1
            liste["articles"][id_] = {
                "nom": art["nom"].strip(),
                "quantite": art.get("quantite", ""),
                "rayon": art.get("rayon", "divers"),
            }
        return "ok"
    if nom == "retirer":
        introuvables = []
        for n in entree["noms"]:
            id_ = trouver(liste, n)
            if id_ is None:
                introuvables.append(n)
            else:
                del liste["articles"][id_]
        return f"introuvables : {', '.join(introuvables)}" if introuvables else "ok"
    if nom == "vider":
        liste["articles"].clear()
        return "ok"
    return f"outil inconnu : {nom}"


SYSTEME = """Tu es l'assistant de courses d'un foyer, sur Telegram.
- Utilise les outils pour modifier la liste dès que l'utilisateur ajoute, retire ou corrige quelque chose.
- Quand on te donne un plat ou une recette, décompose-le en ingrédients avec des quantités adaptées au nombre de personnes (4 par défaut).
- N'ajoute pas les basiques (sel, poivre, huile) sauf si on te le demande ; propose-les plutôt en une phrase.
- Réponds en français, en 1 à 3 phrases maximum. N'affiche pas la liste complète : le bot s'en charge.

Liste actuelle (JSON) :
{liste}"""


async def demander_a_claude(chat_id: int, texte: str) -> str:
    """Un tour de conversation : Claude lit la liste actuelle, appelle les outils, répond."""
    async with verrou:
        data = charger_tout()
        liste = liste_de(data, chat_id)
        messages = [{"role": "user", "content": texte}]

        for _ in range(5):  # garde-fou contre une boucle infinie d'outils
            vue = [{"nom": a["nom"], "quantite": a["quantite"], "rayon": a["rayon"]}
                   for a in liste["articles"].values()]
            rep = await claude.messages.create(
                model=MODELE,
                max_tokens=1024,
                system=SYSTEME.format(liste=json.dumps(vue, ensure_ascii=False)),
                tools=OUTILS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": rep.content})
            if rep.stop_reason != "tool_use":
                break
            resultats = [
                {"type": "tool_result", "tool_use_id": b.id, "content": executer(liste, b.name, b.input)}
                for b in rep.content if b.type == "tool_use"
            ]
            messages.append({"role": "user", "content": resultats})

        sauver_tout(data)
        return "".join(b.text for b in rep.content if b.type == "text").strip() or "C'est noté."


# --- Affichage ---

def rendu_liste(liste: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    articles = liste["articles"]
    if not articles:
        return "🛒 La liste est vide.", None

    par_rayon: dict[str, list[tuple[str, dict]]] = {}
    for id_, art in articles.items():
        par_rayon.setdefault(art["rayon"], []).append((id_, art))

    lignes, boutons = ["🛒 <b>Liste de courses</b>"], []
    ordre = sorted(par_rayon, key=lambda r: RAYONS.index(r) if r in RAYONS else len(RAYONS))
    for rayon in ordre:
        lignes.append(f"\n<b>{html.escape(rayon.capitalize())}</b>")
        for id_, art in sorted(par_rayon[rayon], key=lambda x: x[1]["nom"].lower()):
            qte = f" — {html.escape(art['quantite'])}" if art["quantite"] else ""
            lignes.append(f"• {html.escape(art['nom'])}{qte}")
            boutons.append(InlineKeyboardButton(f"✅ {art['nom']}"[:40], callback_data=f"del:{id_}"))

    clavier = [boutons[i:i + 2] for i in range(0, len(boutons), 2)]
    clavier.append([InlineKeyboardButton("🗑 Tout vider", callback_data="vider")])
    return "\n".join(lignes), InlineKeyboardMarkup(clavier)


def autorise(update: Update) -> bool:
    return not AUTORISES or (update.effective_user and update.effective_user.id in AUTORISES)


# --- Handlers Telegram ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Salut ! Je gère ta liste de courses.\n\n"
        "Écris-moi simplement :\n"
        "• « ajoute du lait et 6 œufs »\n"
        "• « de quoi faire des lasagnes pour 4 »\n"
        "• « retire le beurre »\n\n"
        "/liste — afficher la liste (touche un article pour le cocher)\n"
        "/vider — tout effacer\n"
        "/id — ton identifiant Telegram"
    )


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Ton identifiant : {update.effective_user.id}")


async def cmd_liste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not autorise(update):
        return
    texte, clavier = rendu_liste(liste_de(charger_tout(), update.effective_chat.id))
    await update.message.reply_text(texte, reply_markup=clavier, parse_mode="HTML")


async def cmd_vider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not autorise(update):
        return
    async with verrou:
        data = charger_tout()
        liste_de(data, update.effective_chat.id)["articles"].clear()
        sauver_tout(data)
    await update.message.reply_text("🗑 Liste vidée.")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not autorise(update):
        await update.message.reply_text("Désolé, ce bot est privé.")
        return
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id, "typing")
    try:
        reponse = await demander_a_claude(chat_id, update.message.text)
    except anthropic.APIError:
        log.exception("Erreur API Claude")
        await update.message.reply_text("⚠️ Je n'arrive pas à joindre Claude, réessaie dans un instant.")
        return
    texte, clavier = rendu_liste(liste_de(charger_tout(), chat_id))
    await update.message.reply_text(f"{html.escape(reponse)}\n\n{texte}", reply_markup=clavier, parse_mode="HTML")


async def on_bouton(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not autorise(update):
        await query.answer("Bot privé.")
        return
    chat_id = query.message.chat.id
    async with verrou:
        data = charger_tout()
        liste = liste_de(data, chat_id)
        if query.data == "vider":
            liste["articles"].clear()
            msg = "Liste vidée"
        else:
            art = liste["articles"].pop(query.data.removeprefix("del:"), None)
            msg = f"✅ {art['nom']}" if art else "Déjà retiré"
        sauver_tout(data)
    await query.answer(msg)
    texte, clavier = rendu_liste(liste)
    await query.edit_message_text(texte, reply_markup=clavier, parse_mode="HTML")


def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler(["start", "aide", "help"], cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("liste", cmd_liste))
    app.add_handler(CommandHandler("vider", cmd_vider))
    app.add_handler(CallbackQueryHandler(on_bouton))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("Bot démarré (modèle : %s)", MODELE)
    app.run_polling()


if __name__ == "__main__":
    main()
