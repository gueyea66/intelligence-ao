"""
Scraper Telegram — canaux publics Afrique de l'Ouest (commerce, informel, marché).
Utilise Telethon en mode "invite link" sans abonnement (lecture seule des canaux publics).
Nécessite : TELEGRAM_API_ID, TELEGRAM_API_HASH (depuis https://my.telegram.org)
"""
import os
import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Canaux publics Afrique de l'Ouest — commerce/informel/marché
# Format: username (sans @) ou invite link t.me/+xxx
PUBLIC_CHANNELS = [
    # Sénégal — commerce général
    "senegal_commerce_general",
    "marchesenligne_dakar",
    "vente_achat_senegal",
    "commerce_dakar_officiel",
    "telephones_dakar",
    "electromenager_dakar",
    "immobilier_dakar",
    # Sénégal — produits spécifiques
    "telephone_senegal",
    "informatique_dakar",
    "mode_senegal",
    # Côte d'Ivoire
    "commerce_abidjan",
    "achatventecotedivoire",
    # Mali
    "commerce_bamako",
    # Multi-pays
    "afrique_commerce_west",
    "afrique_import_export",
    "trading_afrique_ouest",
]

# Taille de batch pour ne pas dépasser les rate limits Telegram
BATCH_SIZE = 100
MAX_MESSAGES_PER_CHANNEL = 500  # par run


async def scrape_channel(client, channel_username: str, days_back: int = 7) -> list[dict]:
    """Collecte les messages récents d'un canal public."""
    messages = []
    since = datetime.utcnow() - timedelta(days=days_back)

    try:
        entity = await client.get_entity(channel_username)
        channel_name = getattr(entity, 'title', channel_username)
        channel_id = str(entity.id)

        logger.info(f"Scraping {channel_name} ({channel_id})...")

        async for msg in client.iter_messages(entity, limit=MAX_MESSAGES_PER_CHANNEL, offset_date=None):
            if msg.date and msg.date.replace(tzinfo=None) < since:
                break
            if not msg.text or len(msg.text.strip()) < 10:
                continue

            # Hash auteur (anonymisation)
            sender_id = str(getattr(msg.sender_id, 'user_id', msg.sender_id) or 'unknown')
            auteur_hash = hashlib.sha256(sender_id.encode()).hexdigest()

            messages.append({
                "plateforme": "telegram",
                "canal": channel_name,
                "canal_id": channel_id,
                "message_id": str(msg.id),
                "texte_brut": msg.text.strip(),
                "date_publication": msg.date.replace(tzinfo=None),
                "auteur_hash": auteur_hash,
            })

        logger.info(f"  {len(messages)} messages collectés")

    except Exception as e:
        logger.warning(f"Erreur canal {channel_username}: {e}")

    return messages


async def run_telegram_scraper(
    api_id: int,
    api_hash: str,
    session_file: str = "telegram_session",
    channels: Optional[list[str]] = None,
    days_back: int = 7,
) -> list[dict]:
    """Point d'entrée principal du scraper Telegram."""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        logger.error("Telethon non installé. Lancer: pip install telethon")
        return []

    # Utiliser session string si disponible (pour GitHub Actions)
    session_string = os.environ.get("TELEGRAM_SESSION_STRING", "")
    if session_string:
        session = StringSession(session_string)
    else:
        session = session_file

    client = TelegramClient(session, api_id, api_hash)
    all_messages = []

    try:
        await client.start()
        logger.info("Connecté à Telegram")

        targets = channels or PUBLIC_CHANNELS
        for channel in targets:
            msgs = await scrape_channel(client, channel, days_back)
            all_messages.extend(msgs)
            await asyncio.sleep(1)  # rate limit

    except Exception as e:
        logger.error(f"Erreur Telegram: {e}")
    finally:
        await client.disconnect()

    return all_messages


def scrape_and_store(db_session, days_back: int = 1):
    """
    Scrape + analyse NLP + stocke en DB.
    Déduplication intelligente : ne fetch que les messages depuis le dernier run.
    """
    from src.analytics.nlp_engine import analyze_message
    from src.database.social_models import DiscussionSociale
    from src.scrapers.social.dedup_manager import DedupManager
    from sqlalchemy.exc import IntegrityError

    api_id = int(os.environ.get("TELEGRAM_API_ID", "0"))
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")

    if not api_id or not api_hash:
        logger.error("TELEGRAM_API_ID ou TELEGRAM_API_HASH manquant")
        return 0

    dedup = DedupManager(db_session)
    messages = asyncio.run(run_telegram_scraper(api_id, api_hash, days_back=days_back))
    logger.info(f"Total messages bruts collectés: {len(messages)}")

    # Filtrer les doublons
    new_messages = dedup.filter_new_messages(messages)
    logger.info(f"Nouveaux messages à insérer: {len(new_messages)}")

    inserted = 0
    last_ids: dict[str, str] = {}  # canal_id → dernier message_id

    for msg in new_messages:
        try:
            nlp = analyze_message(msg["texte_brut"])
            record = DiscussionSociale(
                plateforme=msg["plateforme"],
                canal=msg["canal"],
                canal_id=msg["canal_id"],
                message_id=msg["message_id"],
                texte_brut=msg["texte_brut"],
                date_publication=msg["date_publication"],
                auteur_hash=msg["auteur_hash"],
                langue=nlp["langue"],
                sentiment=nlp["sentiment"],
                score_sentiment=nlp["score_sentiment"],
                topics=nlp["topics"],
                pain_points=nlp["pain_points"],
                prix_mentionnes=nlp["prix_mentionnes"],
                type_message=nlp["type_message"],
                contient_prix=nlp["contient_prix"],
                contient_contact=nlp["contient_contact"],
                traite=True,
            )
            db_session.add(record)
            db_session.commit()
            inserted += 1
            last_ids[msg["canal_id"]] = msg["message_id"]
        except IntegrityError:
            db_session.rollback()
        except Exception as e:
            db_session.rollback()
            logger.warning(f"Erreur insertion: {e}")

    # Mettre à jour l'état de dédup par canal
    canal_map = {}
    for msg in messages:
        canal_map[msg["canal_id"]] = msg["canal"]
    for canal_id, last_mid in last_ids.items():
        dedup.update_state("telegram", canal_id, canal_map.get(canal_id, canal_id), last_mid, inserted)

    logger.info(f"{inserted} nouveaux messages insérés ({len(messages) - len(new_messages)} doublons ignorés)")
    return inserted
