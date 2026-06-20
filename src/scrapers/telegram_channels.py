"""
Telegram public channels — scraping sans auth via t.me (web preview).
Channels commerce Sénégal / AO Afrique de l'Ouest.
"""
import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from src.database.db import upsert_informel
from src.database.models import get_session, get_engine, Base, AnnoncInformel
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)
_SOURCE = "Telegram"

# Channels publics pertinents — commerce, prix, AO, import/export AO
_CHANNELS = [
    # Commerce & prix Sénégal
    "senegal_commerce",
    "dakar_deals",
    "marche_senegal",
    "prix_marche_dakar",
    "senegalimportexport",
    "commerceafrique",
    # AO & marchés publics
    "appels_offres_senegal",
    "aosénégal",
    "marchespublicssenegal",
    "aofrique",
    "appelsoffresafrique",
    # Import Chine / sourcing
    "importchinesenegal",
    "chine_afrique_business",
    "alibaba_senegal",
    # Business général AO
    "businessdakar",
    "entrepreneursenegal",
    "pmesenegal",
    "afriquebusiness",
    "businessafrique224",
]

_PRIX_PATTERN = re.compile(
    r"([\d\s]{3,})\s*(F\s*CFA|FCFA|XOF|CFA|FRANC)", re.IGNORECASE
)
_AO_KEYWORDS = re.compile(
    r"(appel\s*d['']offre|avis\s*d['']appel|marchés?\s*public|DAO|DCE|dossier\s*appel)",
    re.IGNORECASE,
)


def _fetch_channel(channel: str, headers: dict) -> list[dict]:
    """Scrape les derniers messages publics d'un channel Telegram."""
    url = f"https://t.me/s/{channel}"
    items = []
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.debug(f"Telegram {channel}: HTTP {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        messages = soup.select(".tgme_widget_message_text")

        for msg in messages[:50]:
            texte = msg.get_text(separator=" ", strip=True)
            if not texte or len(texte) < 15:
                continue

            prix = None
            m = _PRIX_PATTERN.search(texte)
            if m:
                try:
                    prix = float(re.sub(r"\s", "", m.group(1)))
                except ValueError:
                    pass

            # Limiter aux messages avec prix ou mots-clés AO
            if not prix and not _AO_KEYWORDS.search(texte):
                continue

            # Trouver le lien du message
            msg_wrap = msg.find_parent("div", class_="tgme_widget_message_wrap")
            msg_link = ""
            if msg_wrap:
                a = msg_wrap.select_one("a.tgme_widget_message_date")
                msg_link = a.get("href", "") if a else ""

            items.append({
                "source":             f"Telegram @{channel}",
                "date_collecte":      datetime.utcnow(),
                "type":               "offre" if prix else "information",
                "produit":            texte[:200],
                "marque":             "",
                "prix_unitaire":      prix,
                "devise":             "XOF",
                "vendeur_zone":       "Sénégal",
                "contact_disponible": False,
                "url_annonce":        msg_link,
                "notes_terrain":      f"telegram_{channel}",
            })

    except Exception as e:
        logger.debug(f"Telegram {channel}: {e}")

    return items


def run(config=None) -> int:
    if config is None:
        config = load_config()

    Base.metadata.create_all(get_engine(config))
    session = get_session(config)

    headers = {
        "User-Agent": config["scraping"]["user_agent"],
        "Accept-Language": "fr-FR,fr;q=0.9",
    }

    nb_ok = 0
    channels_actifs = 0

    for channel in _CHANNELS:
        items = _fetch_channel(channel, headers)
        if items:
            channels_actifs += 1
            for item in items:
                if upsert_informel(session, item):
                    nb_ok += 1
            logger.info(f"Telegram @{channel}: {len(items)} messages pertinents")

    session.close()
    logger.info(f"Telegram terminé: {nb_ok} messages sur {channels_actifs}/{len(_CHANNELS)} channels actifs")
    return nb_ok
