"""
Dakarois.com — petites annonces Sénégal (alternative à Expat-Dakar).
"""
import logging
import re
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.database.db import upsert_informel

logger = logging.getLogger(__name__)
_SOURCE = "Dakarois"

_CATEGORIES = [
    "/annonces/telephonie-smartphones",
    "/annonces/informatique-multimedia",
    "/annonces/electromenager",
    "/annonces/meubles-decoration",
    "/annonces/habillement-mode",
    "/annonces/alimentation",
    "/annonces/services",
    "/annonces/batiment-btp",
]


class DakaroisScraper(BaseScraper):
    source_nom  = _SOURCE
    source_type = "informel"

    def scrape_items(self) -> Generator[dict, None, None]:
        base = "https://www.dakarois.com"

        for cat in _CATEGORIES:
            for page in range(1, 4):
                sep = "&" if "?" in cat else "?"
                url = f"{base}{cat}{sep}page={page}"
                s = self.soup(url)
                if not s:
                    break

                cards = (
                    s.select(".annonce-item") or
                    s.select(".listing-item") or
                    s.select("article") or
                    s.select("[class*='ad-']")
                )
                if not cards:
                    break

                for card in cards:
                    item = self._parse(card, base, cat)
                    if item:
                        yield item
                self.sleep(1.5)

    def _parse(self, el, base, cat) -> dict | None:
        try:
            titre_el = el.select_one("h2, h3, .title, [class*='title']")
            titre = titre_el.get_text(strip=True) if titre_el else ""
            if not titre or len(titre) < 4:
                return None

            link = el.find("a")
            href = link.get("href", "") if link else ""
            url_ann = href if href.startswith("http") else f"{base}{href}"

            prix = None
            prix_el = el.select_one("[class*='price'], .prix")
            if prix_el:
                m = re.search(r"([\d\s]{3,})", prix_el.get_text())
                if m:
                    try:
                        prix = float(re.sub(r"\s", "", m.group(1)))
                    except ValueError:
                        pass

            zone_el = el.select_one("[class*='location'], [class*='zone'], [class*='city']")
            zone = zone_el.get_text(strip=True)[:50] if zone_el else "Dakar"

            return {
                "source":             _SOURCE,
                "date_collecte":      datetime.utcnow(),
                "type":               "offre",
                "produit":            titre[:200],
                "marque":             "",
                "prix_unitaire":      prix,
                "devise":             "XOF",
                "vendeur_zone":       zone,
                "contact_disponible": True,
                "url_annonce":        url_ann,
                "notes_terrain":      cat.split("/")[-1],
            }
        except Exception as e:
            logger.debug(f"Dakarois parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_informel(self.session_db, item)


def run(config=None) -> int:
    return DakaroisScraper(config).run()
