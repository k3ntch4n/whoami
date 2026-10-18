#!/usr/bin/env python3
"""Surveille YouTube + Google News (Earth Arcade / 지구오락실, An Yujin d'IVE)
et envoie les nouveautés sur Telegram.

Variables d'environnement :
  TELEGRAM_BOT_TOKEN  token du bot (@BotFather)
  TELEGRAM_CHAT_ID    ton chat id
  STATE_FILE          chemin du fichier d'état (défaut : alerts/state.json)
  DRY_RUN=1           affiche les messages au lieu de les envoyer
  TEST_MESSAGE=1      envoie juste un message de test et quitte
"""

import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
STATE_FILE = Path(os.environ.get("STATE_FILE", HERE / "state.json"))
DRY_RUN = os.environ.get("DRY_RUN") == "1"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
GNEWS_LOCALES = {
    "ko": "hl=ko&gl=KR&ceid=KR:ko",
    "en": "hl=en-US&gl=US&ceid=US:en",
    "fr": "hl=fr&gl=FR&ceid=FR:fr",
}
MAX_SEEN = 3000
PENDING_LIVE_TTL = 3 * 24 * 3600


# ---------------------------------------------------------------- utilitaires

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr,en;q=0.8,ko;q=0.6"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def matches(text, keywords):
    low = text.lower()
    return any(k.lower() in low for k in keywords)


def norm_title(title):
    # Google News ajoute " - Nom du média" : on l'enlève pour dédoublonner entre flux
    title = re.sub(r"\s+-\s+[^-]+$", "", title)
    return re.sub(r"\W+", "", title.lower())


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except ValueError:
            print("state.json illisible, on repart de zéro", file=sys.stderr)
    return {}


def save_state(state):
    for key in ("seen_videos", "seen_news"):
        state[key] = state.get(key, [])[-MAX_SEEN:]
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ telegram

def send_telegram(text):
    if DRY_RUN:
        print("---- [DRY RUN] ----\n" + text + "\n")
        return
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    # limite Telegram : 4096 caractères par message
    for i in range(0, len(text), 4000):
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text[i:i + 4000],
            "parse_mode": "HTML",
            "disable_web_page_preview": "false",
        }).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=20) as resp:
            if json.loads(resp.read()).get("ok") is not True:
                raise RuntimeError("Telegram a refusé le message")
        time.sleep(1)


# ------------------------------------------------------------------- youtube

def resolve_channel_id(channel, state):
    if channel.get("channel_id"):
        return channel["channel_id"]
    handle = channel["handle"]
    cache = state.setdefault("channel_ids", {})
    if handle in cache:
        return cache[handle]
    page = fetch(f"https://www.youtube.com/{handle}")
    m = re.search(r'"externalId":"(UC[\w-]{22})"', page) or re.search(r'"channelId":"(UC[\w-]{22})"', page)
    if not m:
        raise RuntimeError(f"impossible de trouver l'ID de la chaîne {handle}")
    cache[handle] = m.group(1)
    return cache[handle]


def parse_youtube_feed(xml_text):
    root = ET.fromstring(xml_text)
    videos = []
    for entry in root.findall("atom:entry", NS):
        group = entry.find("media:group", NS)
        desc = group.findtext("media:description", "", NS) if group is not None else ""
        videos.append({
            "id": entry.findtext("yt:videoId", "", NS),
            "title": entry.findtext("atom:title", "", NS),
            "author": entry.findtext("atom:author/atom:name", "", NS),
            "published": entry.findtext("atom:published", "", NS),
            "description": desc,
        })
    return videos


def live_status(video_id):
    """Retourne ("live", None), ("upcoming", timestamp) ou (None, None)."""
    try:
        page = fetch(f"https://www.youtube.com/watch?v={video_id}")
    except Exception as exc:  # noqa: BLE001
        print(f"  statut live indisponible pour {video_id}: {exc}", file=sys.stderr)
        return None, None
    if '"isLiveNow":true' in page:
        return "live", None
    if '"isUpcoming":true' in page:
        m = re.search(r'"(?:scheduledStartTime|startTime)":"(\d+)"', page)
        return "upcoming", int(m.group(1)) if m else None
    return None, None


def fmt_ts(ts):
    # heure de Paris (UTC+1 / UTC+2), sans dépendance externe
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        return datetime.fromtimestamp(ts, ZoneInfo("Europe/Paris")).strftime("%d/%m à %Hh%M (heure de Paris)")
    except Exception:  # noqa: BLE001
        return time.strftime("%d/%m à %H:%M UTC", time.gmtime(ts))


def video_message(video, label, status, start_ts):
    url = f"https://www.youtube.com/watch?v={video['id']}"
    if status == "live":
        head = "🔴 <b>EN DIRECT maintenant</b>"
    elif status == "upcoming":
        head = "⏰ <b>Live / première programmé</b>"
        if start_ts:
            head += f" — {fmt_ts(start_ts)}"
    else:
        head = "🎬 <b>Nouvelle vidéo</b>"
    return (f"{head}\n📺 {html.escape(label or video['author'])}\n"
            f"<b>{html.escape(video['title'])}</b>\n{url}")


def check_youtube(state, first_run):
    seen = set(state.setdefault("seen_videos", []))
    pending = state.setdefault("pending_lives", {})
    keywords = CONFIG["keywords"]
    messages = []

    for channel in CONFIG["youtube_channels"]:
        label = channel.get("label") or channel.get("handle")
        try:
            cid = resolve_channel_id(channel, state)
            videos = parse_youtube_feed(fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"))
        except Exception as exc:  # noqa: BLE001
            print(f"[youtube] {label}: {exc}", file=sys.stderr)
            continue
        print(f"[youtube] {label}: {len(videos)} vidéos dans le flux")
        for video in reversed(videos):  # plus ancien d'abord
            if not video["id"] or video["id"] in seen:
                continue
            seen.add(video["id"])
            state["seen_videos"].append(video["id"])
            if channel.get("filter", True) and not matches(video["title"] + " " + video["description"], keywords):
                continue
            status, start_ts = live_status(video["id"])
            if status == "upcoming":
                pending[video["id"]] = {"title": video["title"], "label": label, "added": int(time.time())}
            if not first_run:
                messages.append(video_message(video, label, status, start_ts))

    # lives programmés précédemment : on prévient quand ils démarrent
    for vid, info in list(pending.items()):
        if time.time() - info.get("added", 0) > PENDING_LIVE_TTL:
            del pending[vid]
            continue
        status, _ = live_status(vid)
        if status == "live":
            messages.append(video_message({"id": vid, "title": info["title"], "author": ""}, info["label"], "live", None))
            del pending[vid]
        elif status is None:
            del pending[vid]  # terminé ou annulé

    return messages


# ---------------------------------------------------------------------- news

def parse_news_feed(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        source = item.find("source")
        items.append({
            "id": item.findtext("guid") or item.findtext("link", ""),
            "title": item.findtext("title", ""),
            "link": item.findtext("link", ""),
            "source": source.text if source is not None else "",
            "pub": item.findtext("pubDate", ""),
        })
    return items


def pub_ts(item):
    try:
        return email.utils.parsedate_to_datetime(item["pub"]).timestamp()
    except (TypeError, ValueError):
        return 0


def check_news(state, first_run):
    seen = set(state.setdefault("seen_news", []))
    fresh = []

    for feed in CONFIG["news_feeds"]:
        q = urllib.parse.quote(feed["query"] + " when:2d")
        url = f"https://news.google.com/rss/search?q={q}&{GNEWS_LOCALES[feed.get('lang', 'en')]}"
        try:
            items = parse_news_feed(fetch(url))
        except Exception as exc:  # noqa: BLE001
            print(f"[news] {feed['query']}: {exc}", file=sys.stderr)
            continue
        print(f"[news] {feed['query']} ({feed.get('lang')}): {len(items)} articles")
        for item in items:
            keys = {item["id"], norm_title(item["title"])}
            if keys & seen:
                continue
            seen |= keys
            state["seen_news"].extend(keys)
            fresh.append(item)

    if first_run or not fresh:
        return []

    fresh.sort(key=pub_ts, reverse=True)
    fresh = fresh[:CONFIG.get("max_news_per_run", 8)]
    lines = ["📰 <b>Actus Earth Arcade / Yujin</b>"]
    for item in fresh:
        tag = "📅 " if matches(item["title"], CONFIG["event_keywords"]) else "• "
        lines.append(f'{tag}<a href="{html.escape(item["link"], quote=True)}">{html.escape(item["title"])}</a>')
    return ["\n".join(lines)]


# ---------------------------------------------------------------------- main

def main():
    if os.environ.get("TEST_MESSAGE") == "1":
        send_telegram("✅ Le bot d'alertes Earth Arcade / Yujin fonctionne !")
        return

    state = load_state()
    first_run = not state.get("initialized")
    if first_run:
        print("Premier lancement : on mémorise l'existant sans rien envoyer.")

    messages = check_youtube(state, first_run) + check_news(state, first_run)

    if first_run:
        state["initialized"] = True
        messages = ["✅ Alertes activées ! Tu seras prévenu(e) des nouvelles vidéos, lives et actus "
                    "Earth Arcade (지구오락실) et An Yujin (IVE)."]

    for msg in messages:
        send_telegram(msg)
    print(f"{len(messages)} message(s) envoyé(s)")
    # l'état n'est sauvegardé qu'après l'envoi : en cas d'échec Telegram, on retentera au prochain passage
    save_state(state)


if __name__ == "__main__":
    main()
