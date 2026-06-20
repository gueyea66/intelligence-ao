"""
Europages — annuaire B2B européen, fournisseurs exportant vers Afrique de l'Ouest.
URL : https://www.europages.fr
"""
import logging
from datetime import datetime
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from src.database.models import Entreprise, get_session, get_engine, Base
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)
_SOURCE = "Europages"

_RECHERCHES = [
    "import export Afrique Ouest",
    "export Sénégal",
    "électronique Afrique",
    "textile Afrique Ouest",
    "alimentaire export Sénégal",
    "matériaux construction Afrique",
    "fournitures bureau Afrique",
    "équipement industriel Afrique",
]

_BASE = "https://www.europages.fr"


def run(config=None) -> int:
    if config is None:
        config = load_config()

    Base.metadata.create_all(get_engine(config))
    session = get_session(config)

    headers = {
        "User-Agent": config["scraping"]["user_agent"],
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    nb_ok = 0

    for recherche in _RECHERCHES:
        url = f"{_BASE}/recherche/resultat?cserpRedirect=1&q={quote(recherche)}"
        try:
            resp = requests.get(url, headers=headers,
                                timeout=config["scraping"]["timeout"])
            if resp.status_code != 200:
                logger.warning(f"Europages {recherche}: HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = (
                soup.select(".company-card") or
                soup.select("[class*='company-item']") or
                soup.select("article") or
                soup.select("li[class*='result']")
            )

            for card in cards[:20]:
                try:
                    nom_el = card.select_one("h2, h3, [class*='company-name'], [class*='name']")
                    nom = nom_el.get_text(strip=True) if nom_el else ""
                    if not nom or len(nom) < 3:
                        continue

                    pays_el = card.select_one("[class*='country'], [class*='location'], [class*='flag']")
                    pays_src = pays_el.get_text(strip=True)[:50] if pays_el else "Europe"

                    desc_el = card.select_one("[class*='desc'], [class*='activity'], p")
                    desc = desc_el.get_text(strip=True)[:200] if desc_el else ""

                    link = card.find("a")
                    href = link.get("href", "") if link else ""
                    url_ent = href if href.startswith("http") else f"{_BASE}{href}"

                    existing = session.query(Entreprise).filter(Entreprise.nom == nom).first()
                    if existing:
                        continue

                    ent = Entreprise(
                        nom=nom[:200],
                        secteur=recherche[:100],
                        type="exportateur",
                        pays=pays_src,
                        ville="",
                        contact="",
                        notes=f"{desc} | {url_ent}"[:500],
                        source=_SOURCE,
                    )
                    session.add(ent)
                    nb_ok += 1

                except Exception as e:
                    logger.debug(f"Europages card: {e}")

            session.commit()
            logger.info(f"Europages '{recherche}': {nb_ok} total")

        except Exception as e:
            logger.warning(f"Europages '{recherche}': {e}")

    session.close()
    logger.info(f"Europages terminé: {nb_ok} entreprises")
    return nb_ok
