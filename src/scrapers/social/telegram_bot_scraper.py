"""
Telegram scraper via Bot API uniquement.
- Zéro compte personnel, zéro trace
- Le bot est ajouté comme membre dans les groupes/canaux
- Lit les messages via getUpdates / getChatHistory

Setup (une seule fois) :
  1. Ouvrir Telegram → chercher @BotFather → /newbot
  2. Choisir un nom quelconque (ex: "DataFeedBot")
  3. Copier le token → GitHub secret TELEGRAM_BOT_TOKEN
  4. Ajouter le bot en admin dans chaque groupe/canal cible
     (ou juste membre pour les canaux publics)

Canaux publics Afrique Ouest identifiés (peuvent être joints sans admin) :
  @COLOBANE_SANDAGA, @senegalbusiness, @senegaldeals
"""

import os
import json
import hashlib
import logging
import requests
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DAYS_BACK = int(os.environ.get("DAYS_BACK", "1"))

# Canaux/groupes publics à surveiller — le bot doit y être ajouté
# IDs négatifs = groupes, @username = canaux publics
PUBLIC_TARGETS = [
    # Sénégal commerce
    "@COLOBANE_SANDAGA",
    "@senegalbusiness",
    "@senegaldeals",
    # Côte d'Ivoire / Afrique Ouest
    "@venteachattogo",
    "@commerce_ci_officiel",
]

# Chat IDs privés configurés (groups où le bot a été ajouté manuellement)
# Format : "TELEGRAM_CHAT_IDS" = JSON list d'IDs ex: [-100123456, -100654321]
PRIVATE_CHAT_IDS = json.loads(os.environ.get("TELEGRAM_CHAT_IDS", "[]"))


def bot_request(method: str, params: dict = None) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    r = requests.get(url, params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def get_updates(offset: int = 0, limit: int = 100) -> list:
    """Récupère les messages reçus par le bot depuis offset."""
    try:
        data = bot_request("getUpdates", {"offset": offset, "limit": limit, "timeout": 5})
        return data.get("result", [])
    except Exception as e:
        logger.warning(f"getUpdates error: {e}")
        return []


def resolve_channel(username: str) -> dict | None:
    """Obtient les infos d'un canal public par son username."""
    try:
        data = bot_request("getChat", {"chat_id": username})
        if data.get("ok"):
            return data["result"]
    except Exception as e:
        logger.debug(f"Can't resolve {username}: {e}")
    return None


def analyze_text(text: str) -> dict:
    lower = text.lower()
    import re
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
    if not BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN manquant — scraper Telegram désactivé")
        return 0

    from sqlalchemy import text as sql_text
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    inserted = 0

    # 1. Récupérer via getUpdates (messages reçus par le bot)
    updates = get_updates(limit=200)
    messages = []
    for upd in updates:
        msg = upd.get("message") or upd.get("channel_post") or upd.get("edited_message")
        if msg:
            messages.append(msg)

    # 2. Résoudre les canaux publics pour obtenir leur chat_id
    resolved_ids = {}
    for target in PUBLIC_TARGETS:
        info = resolve_channel(target)
        if info:
            resolved_ids[target] = info.get("id")
            logger.info(f"Canal résolu: {target} → {info.get('id')} ({info.get('title', '')})")

    # 3. Insérer les messages
    for msg in messages:
        try:
            text = (
                msg.get("text") or
                msg.get("caption") or
                (msg.get("poll", {}).get("question", "") if "poll" in msg else "")
            )
            if not text or len(text) < 5:
                continue

            ts = datetime.fromtimestamp(msg["date"], tz=timezone.utc)
            if ts < since:
                continue

            chat = msg.get("chat", {})
            canal_id = str(chat.get("id", ""))
            canal_name = chat.get("title") or chat.get("username") or canal_id
            msg_id = str(msg.get("message_id", ""))
            sender = msg.get("from", {}).get("id") or msg.get("sender_chat", {}).get("id") or "unknown"
            author_hash = hashlib.sha256(str(sender).encode()).hexdigest()

            nlp = analyze_text(text)

            try:
                session.execute(sql_text("""
                    INSERT INTO discussions_sociales
                    (plateforme, canal, canal_id, message_id, texte_brut, date_publication,
                     auteur_hash, sentiment, score_sentiment, topics, prix_mentionnes,
                     contient_prix, contient_contact, type_message, traite)
                    VALUES (:pl,:ca,:ci,:mi,:tb,:dp,:ah,:se,:ss,:to,:pr,:cp,:cc,:tm,:tr)
                    ON CONFLICT (plateforme, canal_id, message_id) DO NOTHING
                """), {
                    "pl": "telegram", "ca": canal_name, "ci": canal_id, "mi": msg_id,
                    "tb": text, "dp": ts, "ah": author_hash,
                    "se": nlp["sentiment"], "ss": nlp["score_sentiment"],
                    "to": json.dumps(nlp["topics"]), "pr": json.dumps(nlp["prix_mentionnes"]),
                    "cp": nlp["contient_prix"], "cc": nlp["contient_contact"],
                    "tm": "message", "tr": True
                })
                session.commit()
                inserted += 1
            except Exception:
                session.rollback()
        except Exception as e:
            logger.debug(f"Message skip: {e}")

    logger.info(f"Telegram Bot: {len(messages)} messages reçus, {inserted} insérés")
    return inserted
