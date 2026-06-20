"""
Scraper Facebook Marketplace Dakar — annonces publiques.
Note: FB Marketplace nécessite Playwright (JS dynamique).
      Fallback sur CoinAfrique si FB bloque.
"""
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.database.db import upsert_informel

logger = logging.getLogger(__name__)
_SOURCE_NOM = "Facebook Marketplace Dakar"


class FacebookMarketplaceScraper(BaseScraper):
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
            logger.info(f"{_SOURCE_NOM} désactivé")
            return

        # Facebook exige un login ou bloque les scrapers non-authentifiés.
        # On tente d'abord la version publique mobile (plus légère).
        base_url = "https://m.facebook.com/marketplace/dakar/search"
        categories = ["electronics", "vehicles", "home", "garden", "apparel"]
        delai = src.get("delai_entre_requetes", 5)

        for cat in categories:
            url = f"{base_url}?query={cat}&exact=false"
            s = self.soup(url)
            if not s:
                logger.warning(f"FB Marketplace: pas de réponse pour {cat} — FB bloque probablement")
                continue

            # Tentative de parse des listings mobiles
            listings = (
                s.select("div[data-testid='marketplace_feed_item']") or
                s.select("div[data-pagelet*='Marketplace']") or
                s.select("._4-u2")  # classe mobile historique
            )

            for listing in listings:
                item = self._parse(listing)
                if item:
                    yield item
                self.sleep(0.5)

            self.sleep(delai)

    def _parse(self, el) -> dict | None:
        try:
            text = el.get_text(separator=" ", strip=True)
            if not text or len(text) < 5:
                return None

            # Prix
            import re
            prix = None
            m = re.search(r"([\d\s]{3,})\s*(F\s*CFA|XOF|FCFA|francs?|€|\$)", text, re.IGNORECASE)
            if m:
                try:
                    prix = float(re.sub(r"\s", "", m.group(1)))
                except ValueError:
                    pass

            # Image / lien
            link = el.find("a")
            url_annonce = ""
            if link:
                href = link.get("href", "")
                url_annonce = href if href.startswith("http") else f"https://www.facebook.com{href}"

            return {
                "source":               _SOURCE_NOM,
                "date_collecte":        datetime.utcnow(),
                "type":                 "offre",
                "produit":              text[:100],
                "marque":               "",
                "quantite_disponible":  1,
                "prix_unitaire":        prix,
                "devise":               "XOF",
                "vendeur_zone":         "Dakar",
                "contact_disponible":   True,
                "url_annonce":          url_annonce,
                "notes_terrain":        "",
            }
        except Exception as e:
            logger.debug(f"FB parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_informel(self.session_db, item)


def run(config: dict | None = None) -> int:
    return FacebookMarketplaceScraper(config).run()
