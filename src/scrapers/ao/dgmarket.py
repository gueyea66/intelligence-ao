"""
Scanner DgMarket — appels d'offres internationaux, focus Afrique.
URL : https://www.dgmarket.com
"""
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.scrapers.ao.dcmp import _extract_date, _extract_budget, _guess_categorie
from src.database.db import upsert_ao

logger = logging.getLogger(__name__)
_SOURCE_NOM = "DgMarket"


class DgMarketScraper(BaseScraper):
    source_nom  = _SOURCE_NOM
    source_type = "ao"

    def _src_config(self) -> dict:
        for s in self.config["sources"]["appels_offres"]:
            if s["nom"] == _SOURCE_NOM:
                return s
        raise ValueError(f"Source '{_SOURCE_NOM}' absente de config.yaml")

    @property
    def _headers(self) -> dict:
        return {
            "User-Agent":      self.config["scraping"]["user_agent"],
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Referer":         "https://www.google.com/",
        }

    def scrape_items(self) -> Generator[dict, None, None]:
        src = self._src_config()
        if not src.get("actif", False):
            return

        base_url = src["url"]
        delai    = src.get("delai_entre_requetes", 3)

        pays_cibles = self.config["geo"]["pays_prioritaires"]
        import urllib.parse
        pays_query = urllib.parse.quote(" OR ".join(pays_cibles))

        url = f"{base_url}/tenders?query={pays_query}&type=procurement"
        page = 1

        while page <= 10:
            s = self.soup(f"{url}&page={page}")
            if not s:
                break

            items = (
                s.select(".tender-item") or
                s.select("table tbody tr") or
                s.select(".notice-row")
            )
            if not items:
                break

            for item_el in items:
                item = self._parse(item_el, base_url)
                if item:
                    yield item
                self.sleep(0.3)

            page += 1
            self.sleep(delai)

    def _parse(self, el, base_url: str) -> dict | None:
        try:
            text  = el.get_text(separator=" ", strip=True)
            link  = el.find("a")
            objet = link.get_text(strip=True) if link else text[:200]
            href  = (link.get("href", "") if link else "")
            url_ao = href if href.startswith("http") else f"{base_url}{href}"

            pays_cibles = self.config["geo"]["pays_prioritaires"]
            pays = "Afrique"
            for p in pays_cibles:
                if p.lower() in text.lower():
                    pays = p
                    break

            date_pub   = _extract_date(text, 0)
            date_limit = _extract_date(text, 1)
            jours = max(0, (date_limit - datetime.utcnow()).days) if date_limit else None

            return {
                "source":           _SOURCE_NOM,
                "date_publication": date_pub or datetime.utcnow(),
                "date_limite":      date_limit,
                "jours_restants":   jours,
                "reference":        f"DGM_{hash(objet) & 0xFFFFFF:06X}",
                "objet":            objet,
                "entite":           "",
                "pays":             pays,
                "ville":            "",
                "budget_estime":    _extract_budget(text),
                "devise":           "USD",
                "categorie":        _guess_categorie(objet),
                "url_source":       url_ao,
                "statut":           "nouveau",
                "date_collecte":    datetime.utcnow(),
            }
        except Exception as e:
            logger.debug(f"DgMarket parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_ao(self.session_db, item)


def run(config: dict | None = None) -> int:
    return DgMarketScraper(config).run()
