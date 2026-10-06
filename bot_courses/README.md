# 🛒 Bot Telegram « liste de courses »

Un bot Telegram qui tient ta liste de courses. Tu lui écris en langage naturel, et Claude décompose les recettes en ingrédients et met la liste à jour.

```
Toi : de quoi faire une ratatouille pour 4
Bot : J'ai ajouté les légumes pour la ratatouille. Pense à l'huile d'olive si tu n'en as plus.

      🛒 Liste de courses
      Fruits et légumes
      • aubergine — 1
      • courgette — 2
      • poivron — 2
      • tomate — 4
      [✅ aubergine] [✅ courgette] ...
```

Au magasin, touche ✅ sur un article pour le cocher : il disparaît de la liste.

## Commandes

| Commande | Effet |
|---|---|
| *(texte libre)* | ajouter, retirer, corriger (« ajoute 6 œufs », « retire le lait », « finalement 2 L de lait ») |
| `/liste` | afficher la liste avec ses boutons |
| `/vider` | tout effacer |
| `/id` | afficher ton identifiant Telegram |

💡 **En famille :** ajoute le bot à un groupe Telegram, et tout le monde partage la même liste. Dans un groupe, pense à désactiver le « privacy mode » via @BotFather (`/setprivacy` → Disable) pour que le bot lise les messages.

## Installation

### 1. Créer le bot sur Telegram
1. Ouvre une conversation avec **@BotFather**.
2. Envoie `/newbot`, choisis un nom, puis un identifiant qui finit par `bot`.
3. Copie le **jeton** qu'il te donne (`123456789:ABC...`).

### 2. Obtenir une clé API Claude
Crée une clé sur https://console.anthropic.com (rubrique *API Keys*) et ajoute un peu de crédit. Le modèle utilisé par défaut, Haiku 4.5, coûte une fraction de centime par message.

### 3. Lancer le bot
```bash
cd bot_courses
python3 -m venv .venv
source .venv/bin/activate          # sous Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # puis remplis TELEGRAM_TOKEN et ANTHROPIC_API_KEY
python bot.py
```

Envoie `/start` à ton bot sur Telegram, c'est parti.

### 4. Rendre le bot privé (recommandé)
Sans restriction, n'importe qui trouvant ton bot pourrait l'utiliser avec ta clé API. Envoie `/id` au bot, puis mets ton identifiant (et ceux de ta famille) dans `.env` :
```
ALLOWED_USERS=123456789,987654321
```
Redémarre ensuite le bot.

## Le faire tourner en permanence

Le bot ne répond que tant que `python bot.py` tourne. Pour qu'il soit toujours disponible :
- **Raspberry Pi ou serveur perso** : un service `systemd` ou simplement `tmux`.
- **Hébergeur** : Railway, Render, Fly.io, ou une petite VM. Il faut un *worker* (processus permanent), pas un site web. Définis les trois variables d'environnement dans l'interface de l'hébergeur.

> ⚠️ Les listes sont enregistrées dans `listes.json`. Sur un hébergeur sans disque persistant, elles sont perdues à chaque redémarrage : monte un volume et pointe `LISTES_FILE` dessus.

## Options (`.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `TELEGRAM_TOKEN` | — | jeton @BotFather (obligatoire) |
| `ANTHROPIC_API_KEY` | — | clé API Claude (obligatoire) |
| `ALLOWED_USERS` | *(vide = tous)* | identifiants Telegram autorisés |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | modèle Claude utilisé |
| `LISTES_FILE` | `bot_courses/listes.json` | fichier de sauvegarde |

## Comment ça marche

`bot.py` donne à Claude trois **outils** (`ajouter`, `retirer`, `vider`) et la liste actuelle. Claude choisit les outils à appeler selon ton message, le bot les exécute et enregistre le résultat dans `listes.json`, puis réaffiche la liste triée par rayon. Pour ajouter une fonction (prix estimés, liste de menus de la semaine…), il suffit d'ajouter un outil dans `OUTILS` et sa logique dans `executer()`.
