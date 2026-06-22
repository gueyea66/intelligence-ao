"""
Telethon scraper complet — rejoint les canaux en mute, récupère l'historique,
stocke dans discussions_sociales avec NLP complet.

Setup (une seule fois) :
  1. Obtenir API_ID et API_HASH sur https://my.telegram.org
  2. Générer session string : python -m src.scrapers.social.telethon_full generate_session
  3. Mettre SESSION_STRING dans .env (ou GitHub/Vercel secrets)

Variables d'environnement :
  TELEGRAM_API_ID       — int
  TELEGRAM_API_HASH     — str
  TELEGRAM_SESSION_STRING — str (généré une fois, permanent)
  TELEGRAM_DAYS_BACK    — int (défaut 7)
  TELEGRAM_MAX_MESSAGES — int (défaut 2000 par canal)
"""

import os
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Canaux cibles — commerce Afrique de l'Ouest ─────────────────────────────
# Format : username public (sans @) OU invite link complet t.me/+HASH
CHANNELS_PUBLICS = [
    # Sénégal — confirmés actifs
    "COLOBANE_SANDAGA",
    "senegalbusiness",
    "SenegalAnnonces",
    "senegaldeals",
    "commerce_dakar",
    "telephones_dakar",
    "electromenager_dakar",
    "marchepublicsenegal",
    # Côte d'Ivoire
    "commerce_abidjan",
    "achatventecotedivoire",
    # Multi-pays AO
    "afrique_import_export",
    "trading_afrique_ouest",
]

# Groupes privés via invite link (rejoindre en mute automatiquement)
# Format : lien complet t.me/+XXXX ou t.me/joinchat/XXXX
INVITE_LINKS: list[str] = json.loads(
    os.environ.get("TELEGRAM_INVITE_LINKS", "[]")
)

API_ID    = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH  = os.environ.get("TELEGRAM_API_HASH", "")
SESSION   = os.environ.get("TELEGRAM_SESSION_STRING", "")
DAYS_BACK = int(os.environ.get("TELEGRAM_DAYS_BACK", "7"))
MAX_MSGS  = int(os.environ.get("TELEGRAM_MAX_MESSAGES", "2000"))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_client():
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    if SESSION:
        return TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    # Mode fichier local (dev)
    session_path = os.path.join(os.path.dirname(__file__), "tg_session")
    return TelegramClient(session_path, API_ID, API_HASH)


async def _join_silent(client, link: str) -> Optional[str]:
    """Rejoint un groupe/canal via invite link sans notifier (mute immédiat)."""
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.tl.functions.messages import ImportChatInviteRequest, MuteRequest
    from telethon.tl.types import InputPeerNotifySettings
    from telethon.errors import UserAlreadyParticipantError, InviteHashExpiredError

    try:
        if "joinchat" in link or "/+" in link:
            hash_ = link.split("/+")[-1] if "/+" in link else link.split("joinchat/")[-1]
            result = await client(ImportChatInviteRequest(hash_))
            entity = result.chats[0] if result.chats else None
        else:
            entity = await client.get_entity(link)
            await client(JoinChannelRequest(entity))

        if entity:
            # Mute immédiat — aucune notification
            try:
                await client(MuteRequest(
                    peer=entity,
                    settings=InputPeerNotifySettings(mute_until=2**31 - 1)
                ))
            except Exception:
                pass  # mute optionnel
            return getattr(entity, "username", None) or str(entity.id)
    except UserAlreadyParticipantError:
        return "already_member"
    except InviteHashExpiredError:
        logger.warning(f"Lien expiré : {link}")
    except Exception as e:
        logger.warning(f"Join failed {link}: {e}")
    return None


async def _fetch_channel(client, target, since: datetime, max_msgs: int) -> list[dict]:
    """Récupère les messages d'un canal depuis `since`."""
    from telethon.errors import ChannelPrivateError, FloodWaitError
    import asyncio

    messages = []
    try:
        entity = await client.get_entity(target)
        channel_name  = getattr(entity, "title",    None) or str(target)
        channel_id    = str(getattr(entity, "id",   target))

        count = 0
        async for msg in client.iter_messages(entity, limit=max_msgs, reverse=False):
            if count >= max_msgs:
                break
            if not msg.text or len(msg.text.strip()) < 5:
                continue
            msg_date = msg.date.replace(tzinfo=None) if msg.date else datetime.utcnow()
            if msg_date < since:
                break  # messages triés du plus récent au plus ancien
            sender_raw = str(getattr(msg, "sender_id", "unknown") or "unknown")
            messages.append({
                "plateforme":      "telegram",
                "canal":           channel_name,
                "canal_id":        channel_id,
                "message_id":      str(msg.id),
                "texte_brut":      msg.text.strip(),
                "date_publication": msg_date,
                "auteur_hash":     hashlib.sha256(sender_raw.encode()).hexdigest(),
            })
            count += 1

        logger.info(f"  {channel_name}: {len(messages)} msgs collectés")

    except ChannelPrivateError:
        logger.warning(f"Canal privé inaccessible : {target}")
    except FloodWaitError as e:
        logger.warning(f"FloodWait {e.seconds}s — pause")
        await asyncio.sleep(e.seconds + 5)
    except Exception as e:
        logger.warning(f"Erreur canal {target}: {e}")

    return messages


async def _run(days_back: int, max_msgs: int) -> list[dict]:
    client = _get_client()
    all_messages = []
    since = datetime.utcnow() - timedelta(days=days_back)

    try:
        await client.start()
        logger.info(f"Telethon connecté — scrape {days_back}j, max {max_msgs} msgs/canal")

        # Rejoindre les groupes privés via invite links (mute auto)
        for link in INVITE_LINKS:
            result = await _join_silent(client, link)
            if result and result != "already_member":
                logger.info(f"Rejoint (mute) : {result}")
            await asyncio.sleep(2)

        # Scraper tous les canaux
        targets = CHANNELS_PUBLICS + INVITE_LINKS
        for target in targets:
            msgs = await _fetch_channel(client, target, since, max_msgs)
            all_messages.extend(msgs)
            await asyncio.sleep(1.5)  # rate limit Telegram

    except Exception as e:
        logger.error(f"Erreur Telethon: {e}", exc_info=True)
    finally:
        await client.disconnect()

    return all_messages


# ── Point d'entrée DB ─────────────────────────────────────────────────────────

def scrape_and_store(db_session, days_back: int = DAYS_BACK, max_msgs: int = MAX_MSGS) -> int:
    """Scrape + NLP + insert dans discussions_sociales. Retourne nb insérés."""
    from src.analytics.nlp_engine import analyze_message
    from sqlalchemy import text as sql_text
    from sqlalchemy.exc import IntegrityError

    if not API_ID or not API_HASH:
        logger.error("TELEGRAM_API_ID / TELEGRAM_API_HASH manquants — skip Telethon")
        return 0

    try:
        messages = asyncio.run(_run(days_back, max_msgs))
    except Exception as e:
        logger.error(f"asyncio.run failed: {e}")
        return 0

    logger.info(f"Total brut collecté: {len(messages)} messages")
    inserted = skipped = 0

    for m in messages:
        try:
            nlp = analyze_message(m["texte_brut"])
            db_session.execute(sql_text("""
                INSERT INTO discussions_sociales
                (plateforme, canal, canal_id, message_id, texte_brut, date_publication,
                 auteur_hash, langue, sentiment, score_sentiment, topics, pain_points,
                 prix_mentionnes, contient_prix, contient_contact, type_message, traite)
                VALUES
                (:pl,:ca,:ci,:mi,:tb,:dp,:ah,:la,:se,:ss,:to,:pp,:pr,:cp,:cc,:tm,:tr)
                ON CONFLICT (plateforme, canal_id, message_id) DO NOTHING
            """), {
                "pl": m["plateforme"],
                "ca": m["canal"],
                "ci": m["canal_id"],
                "mi": m["message_id"],
                "tb": m["texte_brut"],
                "dp": m["date_publication"],
                "ah": m["auteur_hash"],
                "la": nlp.get("langue", "fr"),
                "se": nlp["sentiment"],
                "ss": nlp["score_sentiment"],
                "to": json.dumps(nlp["topics"]),
                "pp": json.dumps(nlp.get("pain_points", [])),
                "pr": json.dumps([p["montant"] for p in nlp.get("prix_mentionnes", [])]),
                "cp": nlp["contient_prix"],
                "cc": nlp["contient_contact"],
                "tm": nlp.get("type_message", "message"),
                "tr": True,
            })
            db_session.commit()
            inserted += 1
        except IntegrityError:
            db_session.rollback()
            skipped += 1
        except Exception as e:
            db_session.rollback()
            logger.warning(f"Insert error: {e}")

    logger.info(f"Telethon: {inserted} insérés, {skipped} doublons ignorés")
    return inserted


# ── Génération de session string (run une fois en local) ──────────────────────

async def _generate_session():
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    print(f"\nAPI_ID={API_ID}  API_HASH={API_HASH[:8]}...")
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start()
    session_str = client.session.save()
    print(f"\n✅ SESSION STRING (copier dans .env):\nTELEGRAM_SESSION_STRING={session_str}\n")
    await client.disconnect()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "generate_session":
        asyncio.run(_generate_session())
    else:
        print("Usage: python -m src.scrapers.social.telethon_full generate_session")
