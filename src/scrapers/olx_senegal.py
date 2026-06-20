"""
Scraper OLX Sénégal — marketplace annonces B2C.
URL : https://www.olx.sn
"""
import re
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.database.db import upsert_informel

logger = logging.getLogger(__name__)
_SOURCE_NOM = "OLX Sénégal"

_CATEGORIES = [
    "/telephonie",
    "/electronique-multimedia",
    "/maison-jardin",
    "/vetements-mode",
    "/materiel-professionnel",
]


class OlxSenegalScraper(BaseScraper):
    source_nom  = _SOURCE_NOM
    source_type = "informel"

    def scrape_items(self) -> Generator[dict, None, None]:
        base = "https://sn.olx.com"
        max_pages = 5

        for cat_path in _CATEGORIES:
            for page in range(1, max_pages + 1):
                url = f"{base}{cat_path}/?page={page}"
                s = self.soup(url)
                if not s:
                    break

                cards = (
                    s.select("[data-aut-id='itemBox']") or
                    s.select(".EIR5N") or
                    s.select("li[class*='item']") or
                    s.select("article") or
                    s.select(".listing-item")
                )
                if not cards:
                    break

                for card in cards:
                    item = self._parse(card, base, cat_path.strip("/"))
                    if item:
                        yield item
                self.sleep(2)

    def _parse(self, el, base: str, cat: str) -> dict | None:
        try:
            titre_el = el.select_one("[data-aut-id='itemTitle'], h2, h3, .title")
            titre = titre_el.get_text(strip=True) if titre_el else ""
            if not titre or len(titre) < 5:
                return None

            link = el.find("a")
            href = link.get("href", "") if link else ""
            url_ann = href if href.startswith("http") else f"{base}{href}"

            prix = None
            prix_el = el.select_one("[data-aut-id='itemPrice'], .price, [class*='price']")
            if prix_el:
                m = re.search(r"[\d\s]{3,}", prix_el.get_text())
                if m:
                    try:
                        prix = float(re.sub(r"\s", "", m.group()))
                    except ValueError:
                        pass

            return {
                "source":             _SOURCE_NOM,
                "date_collecte":      datetime.utcnow(),
                "type":               "offre",
                "produit":            titre[:200],
                "marque":             "",
                "prix_unitaire":      prix,
                "devise":             "XOF",
                "vendeur_zone":       "Sénégal",
                "contact_disponible": True,
                "url_annonce":        url_ann,
                "notes_terrain":      cat,
            }
        except Exception as e:
            logger.debug(f"OLX parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_informel(self.session_db, item)


def run(config=None) -> int:
    return OlxSenegalScraper(config).run()
