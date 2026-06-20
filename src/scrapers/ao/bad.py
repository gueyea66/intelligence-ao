"""
Scanner BAD — Banque Africaine de Développement.
URL : https://www.afdb.org/fr/projects-and-operations/procurement
"""
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.scrapers.ao.dcmp import _extract_date, _extract_budget, _guess_categorie
from src.database.db import upsert_ao

logger = logging.getLogger(__name__)
_SOURCE_NOM = "BAD"


class BADScraper(BaseScraper):
    source_nom  = _SOURCE_NOM
    source_type = "ao"

    def _src_config(self) -> dict:
        for s in self.config["sources"]["appels_offres"]:
            if s["nom"] == _SOURCE_NOM:
                return s
        raise ValueError(f"Source '{_SOURCE_NOM}' absente de config.yaml")

    def scrape_items(self) -> Generator[dict, None, None]:
        src = self._src_config()
        if not src.get("actif", False):
            return

        base_url = src["url"]
        delai    = src.get("delai_entre_requetes", 5)
        pays_cfg = self.config["geo"]["pays_prioritaires"]

        listing_paths = [
            "/fr/projects-and-operations/procurement",
            "/en/projects-and-operations/procurement",
        ]

        for path in listing_paths:
            url = f"{base_url}{path}"
            s = self.soup(url)
            if not s:
                continue

            items = (
                s.select(".views-row") or
                s.select("table tbody tr") or
                s.select(".procurement-item")
            )

            if not items:
                continue

            logger.info(f"BAD: {len(items)} notices sur {url}")

            for el in items:
                text = el.get_text(separator=" ", strip=True)
                # Filtrer sur pays cibles
                if not any(p.lower() in text.lower() for p in pays_cfg):
                    continue

                item = self._parse(el, base_url)
                if item:
                    yield item
                self.sleep(0.5)

            break

    def _parse(self, el, base_url: str) -> dict | None:
        try:
            text  = el.get_text(separator=" ", strip=True)
            link  = el.find("a")
            objet = link.get_text(strip=True) if link else text[:200]
            href  = link.get("href", "") if link else ""
            url_ao = href if href.startswith("http") else f"{base_url}{href}"

            pays = "Afrique"
            for p in self.config["geo"]["pays_prioritaires"]:
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
                "reference":        f"BAD_{hash(objet) & 0xFFFFFF:06X}",
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
            logger.debug(f"BAD parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_ao(self.session_db, item)


def run(config: dict | None = None) -> int:
    return BADScraper(config).run()
