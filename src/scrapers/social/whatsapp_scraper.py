"""
WhatsApp scraper — deux modes :

1. EXPORT MANUEL (.txt) → discussions_sociales
   Exporter un groupe WA : ... → Plus → Exporter la discussion → Sans médias
   Puis : python -m src.scrapers.social.whatsapp_scraper /chemin/vers/chat.txt

2. WATCH DOSSIER (automatique)
   Surveille WA_EXPORT_DIR pour de nouveaux .txt et les importe auto.
   Utile quand tu exportes régulièrement.

Variables d'environnement :
  WA_EXPORT_DIR  — dossier à surveiller (défaut: data/whatsapp_exports/)
  WA_ZONE        — zone géographique par défaut (défaut: Dakar)
"""

import os
import re
import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

WA_EXPORT_DIR = os.environ.get("WA_EXPORT_DIR", "data/whatsapp_exports")
WA_ZONE       = os.environ.get("WA_ZONE", "Dakar")

# Formats de date WhatsApp selon la région
DATE_PATTERNS = [
    # Format français : 22/06/2026 à 09:45 - Nom : texte
    re.compile(r'^(\d{1,2}/\d{1,2}/\d{2,4})[, àa]+(\d{1,2}:\d{2})(?:\s*[AP]M)?\s*[-–]\s*(.+?)[\s:：]+(.*)$'),
    # Format anglais : [22/06/2026, 09:45:30] Nom: texte
    re.compile(r'^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?)\]\s+(.+?):\s*(.*)$'),
    # Format iOS : 22/06/2026, 09:45 - Nom : texte
    re.compile(r'^(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2})\s*-\s*(.+?):\s*(.*)$'),
]

SYSTEM_MSG_MARKERS = [
    "a rejoint", "a quitté", "a été ajouté", "a modifié", "chiffrement",
    "Messages et appels", "joined using", "added", "left", "changed",
    "security code", "created group", "a créé le groupe",
]


def _is_system_message(text: str) -> bool:
    return any(m in text for m in SYSTEM_MSG_MARKERS)


def _parse_date(date_str: str, time_str: str) -> Optional[datetime]:
    for fmt in ["%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%m/%d/%y"]:
        try:
            d = datetime.strptime(date_str.strip(), fmt)
            h, m = time_str.strip().split(":")[:2]
            return d.replace(hour=int(h), minute=int(m))
        except Exception:
            continue
    return None


def parse_export_file(filepath: str) -> list[dict]:
    """
    Parse un fichier export WhatsApp .txt.
    Retourne une liste de dicts {sender, text, date, group_name}.
    """
    path = Path(filepath)
    group_name = path.stem.replace("_", " ").replace("-", " ").title()
    messages = []
    current: Optional[dict] = None

    with open(filepath, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue

            matched = False
            for pat in DATE_PATTERNS:
                m = pat.match(line)
                if m:
                    # Sauvegarder le message précédent
                    if current and current["text"].strip():
                        messages.append(current)

                    date_str, time_str, sender, text = m.groups()
                    parsed_date = _parse_date(date_str, time_str)

                    if _is_system_message(text) or _is_system_message(sender):
                        current = None
                        matched = True
                        break

                    current = {
                        "group_name": group_name,
                        "sender": sender.strip(),
                        "text": text.strip(),
                        "date": parsed_date or datetime.utcnow(),
                    }
                    matched = True
                    break

            # Continuation d'un message multiligne
            if not matched and current is not None:
                current["text"] += " " + line.strip()

    if current and current["text"].strip():
        messages.append(current)

    logger.info(f"  {path.name}: {len(messages)} messages parsés")
    return messages


def store_messages(messages: list[dict], db_session, group_name: str = "") -> int:
    """Insert les messages dans discussions_sociales avec NLP."""
    from src.analytics.nlp_engine import analyze_message
    from sqlalchemy import text as sql_text
    from sqlalchemy.exc import IntegrityError

    inserted = skipped = 0
    canal_id = f"wa_{hashlib.sha256(group_name.encode()).hexdigest()[:12]}"

    for m in messages:
        if len(m["text"]) < 5:
            continue
        try:
            nlp = analyze_message(m["text"])
            msg_id = hashlib.sha256(
                f"{m['sender']}{m['date']}{m['text'][:50]}".encode()
            ).hexdigest()[:20]
            author_hash = hashlib.sha256(m["sender"].encode()).hexdigest()

            db_session.execute(sql_text("""
                INSERT INTO discussions_sociales
                (plateforme, canal, canal_id, message_id, texte_brut, date_publication,
                 auteur_hash, langue, sentiment, score_sentiment, topics, pain_points,
                 prix_mentionnes, contient_prix, contient_contact, type_message, traite)
                VALUES
                (:pl,:ca,:ci,:mi,:tb,:dp,:ah,:la,:se,:ss,:to,:pp,:pr,:cp,:cc,:tm,:tr)
                ON CONFLICT (plateforme, canal_id, message_id) DO NOTHING
            """), {
                "pl": "whatsapp",
                "ca": m["group_name"],
                "ci": canal_id,
                "mi": msg_id,
                "tb": m["text"],
                "dp": m["date"],
                "ah": author_hash,
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
            logger.debug(f"WA insert error: {e}")

    logger.info(f"WA {group_name}: {inserted} insérés, {skipped} doublons")
    return inserted


def import_file(filepath: str, db_session) -> int:
    """Import complet d'un fichier .txt WhatsApp → discussions_sociales."""
    messages = parse_export_file(filepath)
    group_name = Path(filepath).stem
    return store_messages(messages, db_session, group_name)


def watch_and_import(db_session) -> int:
    """
    Scanne WA_EXPORT_DIR pour tous les .txt et les importe.
    Idempotent : ON CONFLICT DO NOTHING évite les doublons.
    """
    export_dir = Path(WA_EXPORT_DIR)
    if not export_dir.exists():
        export_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Dossier créé : {export_dir}. Déposer les exports .txt ici.")
        return 0

    txt_files = list(export_dir.glob("*.txt"))
    if not txt_files:
        logger.info(f"Aucun export .txt dans {export_dir}")
        return 0

    total = 0
    for f in txt_files:
        logger.info(f"Import WhatsApp: {f.name}")
        total += import_file(str(f), db_session)

    logger.info(f"WhatsApp watch: {total} messages insérés depuis {len(txt_files)} fichiers")
    return total


def scrape(db_session) -> int:
    """Point d'entrée standard pour main.py scrape --source social."""
    return watch_and_import(db_session)


if __name__ == "__main__":
    import sys
    from src.utils.config_loader import load_config
    from src.database.models import get_session

    config = load_config()
    session = get_session(config)

    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        n = import_file(filepath, session)
        print(f"✅ {n} messages importés depuis {filepath}")
    else:
        n = watch_and_import(session)
        print(f"✅ {n} messages importés depuis {WA_EXPORT_DIR}")

    session.close()
