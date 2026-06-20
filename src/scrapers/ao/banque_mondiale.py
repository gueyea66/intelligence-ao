"""
Scanner Banque Mondiale — projets et appels d'offres.
API publique : https://search.worldbank.org/api/v2/procurement
"""
import logging
from datetime import datetime
from typing import Generator

import requests

from src.scrapers.base_scraper import BaseScraper
from src.scrapers.ao.dcmp import _guess_categorie
from src.database.db import upsert_ao

logger = logging.getLogger(__name__)
_SOURCE_NOM = "Banque Mondiale"

_API_URL = "https://search.worldbank.org/api/v2/procurement"
_COUNTRY_CODES = {
    "Sénégal": "SN", "Côte d'Ivoire": "CI", "Mali": "ML",
    "Burkina Faso": "BF", "Guinée": "GN", "Togo": "TG",
    "Bénin": "BJ", "Niger": "NE",
}


class BanqueMondialeScraper(BaseScraper):
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

        delai    = src.get("delai_entre_requetes", 5)
        pays_cfg = self.config["geo"]["pays_prioritaires"]

        for pays_nom in pays_cfg:
            code = _COUNTRY_CODES.get(pays_nom)
            if not code:
                continue

            params = {
                "format":       "json",
                "country_code": code,
                "strdate":      "2024-01-01",
                "rows":         50,
                "os":           0,
            }

            try:
                resp = requests.get(
                    _API_URL,
                    params=params,
                    headers={"User-Agent": self.config["scraping"]["user_agent"]},
                    timeout=self.config["scraping"]["timeout"],
                )
                if resp.status_code != 200:
                    logger.warning(f"BM API {pays_nom}: HTTP {resp.status_code}")
                    continue

                data = resp.json()
                notices = data.get("procnotices", {}).get("procnotice", [])
                if isinstance(notices, dict):
                    notices = [notices]

                logger.info(f"BM {pays_nom}: {len(notices)} notices")

                for n in notices:
                    item = self._parse(n, pays_nom)
                    if item:
                        yield item

                self.sleep(delai)

            except Exception as e:
                logger.error(f"BM {pays_nom}: {e}")

    def _parse(self, n: dict, pays_nom: str) -> dict | None:
        try:
            objet = n.get("project_name", "") or n.get("noticetext", "")[:200]
            ref   = n.get("noticeno", f"BM_{hash(objet) & 0xFFFFFF:06X}")

            date_pub = _parse_bm_date(n.get("publishdate"))
            date_lim = _parse_bm_date(n.get("deadline"))

            jours = None
            if date_lim:
                jours = max(0, (date_lim - datetime.utcnow()).days)

            budget = None
            try:
                budget = float(n.get("totalamt", 0) or 0)
            except (TypeError, ValueError):
                pass

            return {
                "source":           _SOURCE_NOM,
                "date_publication": date_pub or datetime.utcnow(),
                "date_limite":      date_lim,
                "jours_restants":   jours,
                "reference":        ref,
                "objet":            objet,
                "entite":           n.get("borrower", ""),
                "pays":             pays_nom,
                "ville":            "",
                "budget_estime":    budget,
                "devise":           "USD",
                "categorie":        _guess_categorie(objet),
                "url_source":       n.get("url", ""),
                "statut":           "nouveau",
                "date_collecte":    datetime.utcnow(),
            }
        except Exception as e:
            logger.debug(f"BM parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_ao(self.session_db, item)


def _parse_bm_date(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass
    return None


def run(config: dict | None = None) -> int:
    return BanqueMondialeScraper(config).run()
