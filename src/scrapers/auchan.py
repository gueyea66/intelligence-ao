"""
Scraper Auchan Sénégal — catalogue produits.
URL : https://www.auchan.sn
"""
import re
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.database.db import upsert_produit

logger = logging.getLogger(__name__)
_SOURCE_NOM = "Auchan Sénégal"


class AuchanScraper(BaseScraper):
    source_nom  = _SOURCE_NOM
    source_type = "ecommerce"

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
        max_pages = src.get("max_pages", 30)
        delai     = src.get("delai_entre_requetes", 3)

        # Auchan SN utilise une structure de catalogue paginé
        categories_paths = [
            "/alimentaire",
            "/boissons",
            "/hygiene-beaute",
            "/maison",
            "/electromenager",
            "/informatique",
            "/produits-frais",
        ]

        for cat_path in categories_paths:
            cat_nom = cat_path.lstrip("/").replace("-", " ").title()
            for page in range(1, max_pages + 1):
                url = f"{base_url}{cat_path}?page={page}"
                s = self.soup(url)
                if not s:
                    break

                produits = (
                    s.select(".product-miniature") or
                    s.select(".product-item") or
                    s.select("article.product") or
                    s.select("[class*='product-card']")
                )

                if not produits:
                    break

                logger.info(f"Auchan {cat_nom} page {page}: {len(produits)} produits")

                for el in produits:
                    item = self._parse(el, base_url, cat_nom)
                    if item:
                        yield item
                    self.sleep(0.3)

                self.sleep(delai)

    def _parse(self, el, base_url: str, categorie: str) -> dict | None:
        try:
            nom_el  = el.select_one(".product-title, .product-name, h2, h3, [class*='title']")
            prix_el = el.select_one(".price, [class*='price'], .product-price")
            link    = el.find("a")

            if not nom_el:
                return None

            nom = nom_el.get_text(strip=True)
            parts = nom.split(" ", 1)
            marque = parts[0] if len(parts) > 1 else ""
            modele = parts[1] if len(parts) > 1 else nom

            prix = None
            if prix_el:
                prix_text = prix_el.get_text(strip=True)
                m = re.search(r"([\d\s]+)", prix_text.replace(",", "").replace(".", ""))
                if m:
                    try:
                        prix = float(re.sub(r"\s", "", m.group(1)))
                    except ValueError:
                        pass

            url_produit = ""
            if link:
                href = link.get("href", "")
                url_produit = href if href.startswith("http") else f"{base_url}{href}"

            return {
                "source":       _SOURCE_NOM,
                "date_collecte": datetime.utcnow(),
                "categorie_1":   categorie,
                "categorie_2":   "",
                "marque":        marque,
                "modele":        modele,
                "description":   nom,
                "prix_actuel":   prix,
                "prix_barre":    None,
                "promotion":     False,
                "devise":        "XOF",
                "pays":          "Sénégal",
                "url_source":    url_produit,
                "disponibilite": "En stock",
            }
        except Exception as e:
            logger.debug(f"Auchan parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_produit(self.session_db, item)


def run(config: dict | None = None) -> int:
    return AuchanScraper(config).run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
