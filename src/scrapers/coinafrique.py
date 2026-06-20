"""
Scraper CoinAfrique Sénégal — annonces B2C/B2B.
URL : https://sn.coinafrique.com
"""
import re
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.database.db import upsert_informel

logger = logging.getLogger(__name__)
_SOURCE_NOM = "CoinAfrique Sénégal"


class CoinAfriqueScraper(BaseScraper):
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

        # CoinAfrique — nouvelle structure URL (catégories sous /annonce/{slug})
        cats = [
            "/annonce/telephones",
            "/annonce/electronique",
            "/annonce/electromenager",
            "/annonce/vetements-femme",
            "/annonce/vetements-homme",
            "/annonce/materiaux-et-outillage",
            "/annonce/meubles-et-decoration",
            "/annonce/informatique",
        ]

        for cat in cats:
            for page in range(1, max_pages + 1):
                url = f"{base_url}{cat}?page={page}"
                s = self.soup(url)
                if not s:
                    break

                cards = (
                    s.select(".card") or
                    s.select(".ad-card") or
                    s.select("article.listing") or
                    s.select("[class*='product']")
                )
                if not cards:
                    break

                for card in cards:
                    item = self._parse(card, base_url, cat.lstrip("/"))
                    if item:
                        yield item
                    self.sleep(0.2)

                self.sleep(delai)

    def _parse(self, el, base_url: str, cat: str) -> dict | None:
        try:
            text  = el.get_text(separator=" ", strip=True)
            link  = el.find("a")
            titre = link.get_text(strip=True) if link else text[:100]
            href  = link.get("href", "") if link else ""
            url_annonce = href if href.startswith("http") else f"{base_url}{href}"

            prix = None
            m = re.search(r"([\d\s]{3,})\s*(F\s*CFA|XOF|FCFA|CFA)", text, re.IGNORECASE)
            if m:
                try:
                    prix = float(re.sub(r"\s", "", m.group(1)))
                except ValueError:
                    pass

            zone = "Dakar"
            zones = self.config.get("geo", {}).get("zones_informel", [])
            for z in zones:
                if isinstance(z, dict) and z.get("nom", "").lower() in text.lower():
                    zone = z["nom"]
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
                "notes_terrain":        cat,
            }
        except Exception as e:
            logger.debug(f"CoinAfrique parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_informel(self.session_db, item)


def run(config: dict | None = None) -> int:
    return CoinAfriqueScraper(config).run()
