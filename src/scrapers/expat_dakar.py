"""
Scraper Expat-Dakar.com — petites annonces Sénégal (immobilier, véhicules, services).
URL : https://www.expat-dakar.com
Pas d'auth requise. Données réelles accessibles.
"""
import re
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.database.db import upsert_informel

logger = logging.getLogger(__name__)
_SOURCE_NOM = "Expat-Dakar"

_CATEGORIES = [
    "telephones-tablettes",
    "informatique",
    "electromenager",
    "decoration-linge-de-maison",
    "jardinage-bricolage",
    "vetements-homme",
    "alimentation",
    "emploi-conseil-strategie",
    "vehicules",
    "immobilier",
]


class ExpatDakarScraper(BaseScraper):
    source_nom  = _SOURCE_NOM
    source_type = "informel"

    def scrape_items(self) -> Generator[dict, None, None]:
        base = "https://www.expat-dakar.com"
        max_pages = 5

        for cat_path in _CATEGORIES:
            for page in range(1, max_pages + 1):
                base_url = f"{base}/annonces?category={cat_path}"
                url = f"{base_url}&page={page}" if page > 1 else base_url
                s = self.soup(url)
                if not s:
                    break

                cards = (
                    s.select(".listing-item") or
                    s.select(".ad-item") or
                    s.select("article") or
                    s.select("[class*='item']")
                )
                if not cards:
                    break

                for card in cards:
                    item = self._parse(card, base, cat_path.strip("/"))
                    if item:
                        yield item
                self.sleep(1.5)

    def _parse(self, el, base: str, cat: str) -> dict | None:
        try:
            titre_el = el.select_one("h2, h3, .title, .name, [class*='title']")
            titre = titre_el.get_text(strip=True) if titre_el else el.get_text(separator=" ", strip=True)[:100]
            if not titre or len(titre) < 5:
                return None

            link = el.find("a")
            href = link.get("href", "") if link else ""
            url_ann = href if href.startswith("http") else f"{base}{href}"

            prix = None
            prix_el = el.select_one("[class*='price'], .price, .prix")
            txt_prix = prix_el.get_text() if prix_el else el.get_text()
            m = re.search(r"([\d\s]{3,})\s*(F\s*CFA|FCFA|XOF|CFA|€|\$)", txt_prix, re.IGNORECASE)
            if m:
                try:
                    prix = float(re.sub(r"\s", "", m.group(1)))
                    devise = "XOF" if "CFA" in m.group(2).upper() or "F" in m.group(2).upper() else m.group(2).strip()
                except ValueError:
                    devise = "XOF"
            else:
                devise = "XOF"

            zone = "Dakar"
            loc_el = el.select_one("[class*='location'], [class*='place'], [class*='city']")
            if loc_el:
                zone = loc_el.get_text(strip=True)[:50]

            return {
                "source":             _SOURCE_NOM,
                "date_collecte":      datetime.utcnow(),
                "type":               "offre",
                "produit":            titre[:200],
                "marque":             "",
                "prix_unitaire":      prix,
                "devise":             devise,
                "vendeur_zone":       zone,
                "contact_disponible": True,
                "url_annonce":        url_ann,
                "notes_terrain":      cat,
            }
        except Exception as e:
            logger.debug(f"ExpatDakar parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_informel(self.session_db, item)


def run(config=None) -> int:
    return ExpatDakarScraper(config).run()
