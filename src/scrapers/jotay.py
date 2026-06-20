"""
Scraper Jotay.net — petites annonces Sénégal.
"""
import re
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.database.db import upsert_informel

logger = logging.getLogger(__name__)
_SOURCE_NOM = "Jotay"


class JotayScraper(BaseScraper):
    source_nom  = _SOURCE_NOM
    source_type = "informel"

    def _src_config(self) -> dict:
        for s in self.config["sources"]["ecommerce"]:
            if s["nom"] == _SOURCE_NOM:
                return s
        raise ValueError(f"Source '{_SOURCE_NOM}' absente de config.yaml")

    def scrape_items(self) -> Generator[dict, None, None]:
        src = self._src_config()
        if not src.get("actif", False):
            return

        base_url  = src["url"]
        max_pages = src.get("max_pages", 20)
        delai     = src.get("delai_entre_requetes", 2)

        categories_paths = [
            "/annonces/electronique",
            "/annonces/electromenager",
            "/annonces/vehicules",
            "/annonces/immobilier",
            "/annonces/services",
            "/annonces",
        ]

        for path in categories_paths:
            for page in range(1, max_pages + 1):
                sep = "?" if "?" not in path else "&"
                url = f"{base_url}{path}{sep}page={page}"
                s = self.soup(url)
                if not s:
                    break

                listings = (
                    s.select(".ad-item") or
                    s.select(".annonce") or
                    s.select("article") or
                    s.select(".listing")
                )
                if not listings:
                    break

                for el in listings:
                    item = self._parse(el, base_url)
                    if item:
                        yield item
                    self.sleep(0.3)

                self.sleep(delai)

    def _parse(self, el, base_url: str) -> dict | None:
        try:
            text  = el.get_text(separator=" ", strip=True)
            link  = el.find("a")
            titre = link.get_text(strip=True) if link else text[:100]
            href  = link.get("href", "") if link else ""
            url_annonce = href if href.startswith("http") else f"{base_url}{href}"

            prix = None
            m = re.search(r"([\d\s]{3,})\s*(F\s*CFA|XOF|FCFA)", text, re.IGNORECASE)
            if m:
                try:
                    prix = float(re.sub(r"\s", "", m.group(1)))
                except ValueError:
                    pass

            zone = "Dakar"
            zones = ["Dakar", "Thiès", "Saint-Louis", "Touba", "Kaolack", "Ziguinchor"]
            for z in zones:
                if z.lower() in text.lower():
                    zone = z
                    break

            return {
                "source":               _SOURCE_NOM,
                "date_collecte":        datetime.utcnow(),
                "type":                 "offre",
                "produit":              titre,
                "marque":               "",
                "quantite_disponible":  1,
                "prix_unitaire":        prix,
                "devise":               "XOF",
                "vendeur_zone":         zone,
                "contact_disponible":   True,
                "url_annonce":          url_annonce,
                "notes_terrain":        "",
            }
        except Exception as e:
            logger.debug(f"Jotay parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_informel(self.session_db, item)


def run(config: dict | None = None) -> int:
    return JotayScraper(config).run()
