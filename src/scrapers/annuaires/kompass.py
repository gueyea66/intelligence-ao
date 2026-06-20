"""
Scraper Kompass Afrique de l'Ouest — annuaire B2B entreprises.
URL : https://fr.kompass.com
Données publiques accessibles sans auth.
"""
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.database.models import Entreprise, get_session, get_engine, Base

logger = logging.getLogger(__name__)
_SOURCE_NOM = "Kompass"

_RECHERCHES = [
    ("Sénégal",       "SN", ["import-export", "electronique", "textile", "alimentaire", "batiment"]),
    ("Côte d'Ivoire", "CI", ["import-export", "cacao", "bois", "electronique"]),
    ("Mali",          "ML", ["import-export", "or", "coton", "alimentaire"]),
    ("Ghana",         "GH", ["import-export", "cacao", "electronique"]),
]


class KompassScraper(BaseScraper):
    source_nom  = _SOURCE_NOM
    source_type = "entreprise"

    def scrape_items(self) -> Generator[dict, None, None]:
        base = "https://fr.kompass.com"

        for pays, code, secteurs in _RECHERCHES:
            for secteur in secteurs[:2]:  # limiter pour MVP
                url = f"{base}/searchCompanies?text={secteur}&country={code}&size=25"
                s = self.soup(url)
                if not s:
                    continue

                cards = (
                    s.select(".company-card") or
                    s.select("[class*='company']") or
                    s.select("article") or
                    s.select("li[class*='result']")
                )

                for card in cards:
                    item = self._parse(card, pays, secteur)
                    if item:
                        yield item
                self.sleep(2)

    def _parse(self, el, pays: str, secteur: str) -> dict | None:
        try:
            nom_el = el.select_one("h2, h3, .company-name, [class*='name']")
            nom = nom_el.get_text(strip=True) if nom_el else ""
            if not nom or len(nom) < 3:
                return None

            ville_el = el.select_one("[class*='city'], [class*='address'], [class*='location']")
            ville = ville_el.get_text(strip=True)[:100] if ville_el else ""

            contact_el = el.select_one("[class*='phone'], [class*='tel'], [href^='tel:']")
            contact = contact_el.get_text(strip=True) if contact_el else ""

            link = el.find("a")
            href = link.get("href", "") if link else ""

            return {
                "nom":      nom[:200],
                "secteur":  secteur,
                "type":     "importateur",
                "pays":     pays,
                "ville":    ville[:100],
                "contact":  contact[:100],
                "source":   _SOURCE_NOM,
                "notes":    href[:200],
            }
        except Exception as e:
            logger.debug(f"Kompass parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        try:
            from src.database.models import Entreprise
            Base.metadata.create_all(get_engine(self.config))
            existing = self.session_db.query(Entreprise).filter(Entreprise.nom == item["nom"]).first()
            if existing:
                return False
            ent = Entreprise(**{k: v for k, v in item.items() if hasattr(Entreprise, k)})
            self.session_db.add(ent)
            self.session_db.commit()
            return True
        except Exception as e:
            logger.debug(f"Kompass save: {e}")
            self.session_db.rollback()
            return False


def run(config=None) -> int:
    return KompassScraper(config).run()
