"""
Telegram scraper — canaux publics Afrique de l'Ouest.

Stratégie : scraping HTML de t.me/s/CHANNEL (contenu public, zéro auth, zéro trace).
Le bot token (TELEGRAM_BOT_TOKEN) sert uniquement à valider l'accès et pour les
groupes privés où le bot a été ajouté manuellement.

Canaux cibles : commerce Sénégal / Côte d'Ivoire / Togo
"""

import os
import re
import json
import hashlib
import logging
import requests
from datetime import datetime, timedelta, timezone
from html import unescape

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DAYS_BACK = int(os.environ.get("DAYS_BACK", "1"))

# Canaux publics à scraper via t.me/s/USERNAME
PUBLIC_CHANNELS = [
    "COLOBANE_SANDAGA",
    "senegalbusiness",
    "senegaldeals",
    "venteachattogo",
    "marchepublicsenegal",
    "SenegalAnnonces",
    "commerce_dakar",
]

# Groupes privés où le bot est membre (chat_id négatif)
PRIVATE_CHAT_IDS = json.loads(os.environ.get("TELEGRAM_CHAT_IDS", "[]"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def scrape_public_channel(username: str, days_back: int = 1) -> list:
    """Scrape les messages récents d'un canal public via t.me/s/."""
    url = f"https://t.me/s/{username}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            logger.debug(f"{username}: HTTP {r.status_code}")
            return []
    except Exception as e:
        logger.debug(f"{username}: {e}")
        return []

    html = r.text
    messages = []
    since = datetime.now(timezone.utc) - timedelta(days=days_back)

    # Parser les blocs message
    # Format: <div class="tgme_widget_message" data-post="CHANNEL/ID" ...>
    post_blocks = re.findall(
        r'<div class="tgme_widget_message_wrap[^"]*">(.*?)</div>\s*</div>\s*</div>',
        html, re.DOTALL
    )

    for block in post_blocks:
        try:
            # ID du message
            mid_m = re.search(r'data-post="[^/]+/(\d+)"', block)
            if not mid_m:
                mid_m = re.search(r'data-post=\'[^/]+/(\d+)\'', html)
            msg_id = mid_m.group(1) if mid_m else None

            # Timestamp
            ts_m = re.search(r'datetime="([^"]+)"', block)
            if not ts_m:
                continue
            ts = datetime.fromisoformat(ts_m.group(1).replace('Z', '+00:00'))
            if ts < since:
                continue

            # Texte
            text_m = re.search(
                r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                block, re.DOTALL
            )
            if not text_m:
                continue
            raw = text_m.group(1)
            # Nettoyer HTML
            text = re.sub(r'<[^>]+>', ' ', raw)
            text = unescape(text).strip()
            text = re.sub(r'\s+', ' ', text)

            if len(text) < 5:
                continue

            messages.append({
                "channel": username,
                "channel_id": f"tme_{username}",
                "msg_id": msg_id or f"{username}_{ts.timestamp()}",
                "text": text,
                "ts": ts,
            })
        except Exception:
            continue

    logger.info(f"t.me/s/{username}: {len(messages)} messages (< {days_back}j)")
    return messages


def bot_request(method: str, params: dict = None) -> dict:
    if not BOT_TOKEN:
        return {}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    r = requests.get(url, params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def get_bot_updates(limit: int = 200) -> list:
    """Messages reçus par le bot (groupes privés où il a été ajouté)."""
    if not BOT_TOKEN:
        return []
    try:
        data = bot_request("getUpdates", {"limit": limit, "timeout": 3})
        msgs = []
        for upd in data.get("result", []):
            msg = upd.get("message") or upd.get("channel_post")
            if msg:
                msgs.append(msg)
        return msgs
    except Exception as e:
        logger.debug(f"getUpdates: {e}")
        return []


def analyze_text(text: str) -> dict:
    lower = text.lower()
    price_pattern = re.compile(r'(\d[\d\s,.]*)\s*(fcfa|cfa|xof|f\b|francs?)', re.IGNORECASE)
    prices = []
    for m in price_pattern.finditer(text):
        try:
            val = int(re.sub(r'[\s,.]', '', m.group(1)))
            if 100 <= val <= 100_000_000:
                prices.append(val)
        except Exception:
            pass

    pos = ['bon', 'bien', 'super', 'excellent', 'rapide', 'merci', 'top', 'qualité', 'fiable']
    neg = ['arnaque', 'problème', 'mauvais', 'cher', 'lent', 'faux', 'escroquerie', 'vol']
    ps = sum(1 for w in pos if w in lower)
    ns = sum(1 for w in neg if w in lower)
    sentiment = 'positif' if ps > ns else 'negatif' if ns > ps else 'neutre'

    topics = []
    if re.search(r'télépho|iphone|samsung|android|smartphone', text, re.I): topics.append('electronique')
    if re.search(r'riz|huile|sucre|farine|alimentaire|viande|poisson', text, re.I): topics.append('alimentaire')
    if re.search(r'voiture|moto|transport|véhicule', text, re.I): topics.append('transport')
    if re.search(r'appartement|maison|louer|location|terrain', text, re.I): topics.append('immobilier')
    if re.search(r'prix|vente|achat|vendre|acheter|commande', text, re.I): topics.append('commerce')
    if re.search(r'habit|robe|chaussure|mode|vêtement', text, re.I): topics.append('textile')

    return {
        "sentiment": sentiment,
        "score_sentiment": round((ps - ns) / 5, 2),
        "prix_mentionnes": prices,
        "topics": topics,
        "contient_prix": len(prices) > 0,
        "contient_contact": bool(re.search(r'\+?\d{8,}', text)),
    }


def scrape(session, days_back: int = DAYS_BACK) -> int:
    """Point d'entrée principal — retourne le nombre de messages insérés."""
    from sqlalchemy import text as sql_text

    logger.info("=== Scraping Telegram (canaux publics + bot) ===")
    inserted = 0
    all_messages = []

    # 1. Canaux publics via t.me/s/
    for channel in PUBLIC_CHANNELS:
        msgs = scrape_public_channel(channel, days_back)
        all_messages.extend(msgs)

    # 2. Bot updates (groupes privés)
    for upd_msg in get_bot_updates():
        chat = upd_msg.get("chat", {})
        text = upd_msg.get("text") or upd_msg.get("caption", "")
        if not text or len(text) < 5:
            continue
        ts = datetime.fromtimestamp(upd_msg["date"], tz=timezone.utc)
        all_messages.append({
            "channel": chat.get("title") or chat.get("username") or str(chat.get("id")),
            "channel_id": str(chat.get("id")),
            "msg_id": str(upd_msg.get("message_id")),
            "text": text,
            "ts": ts,
        })

    # 3. Insérer
    for m in all_messages:
        try:
            nlp = analyze_text(m["text"])
            author_hash = hashlib.sha256(m["channel_id"].encode()).hexdigest()
            session.execute(sql_text("""
                INSERT INTO discussions_sociales
                (plateforme, canal, canal_id, message_id, texte_brut, date_publication,
                 auteur_hash, sentiment, score_sentiment, topics, prix_mentionnes,
                 contient_prix, contient_contact, type_message, traite)
                VALUES (:pl,:ca,:ci,:mi,:tb,:dp,:ah,:se,:ss,:to,:pr,:cp,:cc,:tm,:tr)
                ON CONFLICT (plateforme, canal_id, message_id) DO NOTHING
            """), {
                "pl": "telegram", "ca": m["channel"], "ci": m["channel_id"],
                "mi": m["msg_id"], "tb": m["text"], "dp": m["ts"],
                "ah": author_hash, "se": nlp["sentiment"], "ss": nlp["score_sentiment"],
                "to": json.dumps(nlp["topics"]), "pr": json.dumps(nlp["prix_mentionnes"]),
                "cp": nlp["contient_prix"], "cc": nlp["contient_contact"],
                "tm": "message", "tr": True
            })
            session.commit()
            inserted += 1
        except Exception:
            session.rollback()

    logger.info(f"Telegram: {len(all_messages)} messages collectés, {inserted} insérés")
    return inserted
