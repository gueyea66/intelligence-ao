"""
Scraper BCEAO — Banque Centrale des États de l'Afrique de l'Ouest.
Collecte les publications et indicateurs financiers disponibles publiquement.
"""
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from src.database.models import EtudeConjoncture, DonneeMacro, get_session, get_engine, Base
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)

_BCEAO_BASE = "https://www.bceao.int"
_PAGES = [
    "/index.php/publications/publications-periodiques",
    "/index.php/statistiques",
]


def run(config: dict | None = None) -> int:
    if config is None:
        config = load_config()

    session = get_session(config)
    Base.metadata.create_all(get_engine(config))

    headers = {
        "User-Agent":      config["scraping"]["user_agent"],
        "Accept-Language": "fr-FR,fr;q=0.9",
    }
    nb_ok = 0

    for page_url in _PAGES:
        try:
            url = f"{_BCEAO_BASE}{page_url}"
            resp = requests.get(url, headers=headers, timeout=config["scraping"]["timeout"])
            if resp.status_code != 200:
                logger.warning(f"BCEAO {url}: HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extraire les liens publications
            links = soup.select("a[href*='.pdf'], a[href*='publication'], a[href*='rapport'], a[href*='bulletin']")
            for link in links[:20]:
                titre = link.get_text(strip=True)
                if len(titre) < 10:
                    continue
                href = link.get("href", "")
                url_doc = href if href.startswith("http") else f"{_BCEAO_BASE}{href}"

                etude = EtudeConjoncture(
                    source          = "BCEAO",
                    date_collecte   = datetime.utcnow(),
                    titre           = titre[:500],
                    pays            = "UEMOA",
                    themes          = '["Finance","Monnaie","Commerce"]',
                    url_source      = url,
                    url_pdf         = url_doc if ".pdf" in url_doc else None,
                    langue          = "fr",
                )
                session.add(etude)
                nb_ok += 1

            session.commit()
            logger.info(f"BCEAO {page_url}: {nb_ok} publications")

        except Exception as e:
            logger.warning(f"BCEAO {page_url}: {e}")

    session.close()
    return nb_ok
