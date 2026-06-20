"""
Scanner UNGM — United Nations Global Marketplace.
AO des agences ONU (PNUD, UNICEF, PAM, OMS...).
URL : https://www.ungm.org/Public/Notice
"""
import re
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.scrapers.ao.dcmp import _extract_date, _extract_budget, _guess_categorie, _parse_row
from src.database.db import upsert_ao

logger = logging.getLogger(__name__)
_SOURCE_NOM = "UNGM"

_AGENCES_ONU = {
    "UNDP": "PNUD", "UNICEF": "UNICEF", "WFP": "PAM", "WHO": "OMS",
    "UNHCR": "UNHCR", "FAO": "FAO", "ILO": "OIT", "UNESCO": "UNESCO",
    "UNFPA": "UNFPA", "UNOPS": "UNOPS", "UNIDO": "ONUDI",
}

_PAYS_AFRIQUE_OUEST = [
    "Sénégal", "Senegal", "Côte d'Ivoire", "Ivory Coast", "Mali",
    "Burkina Faso", "Guinée", "Guinea", "Togo", "Bénin", "Benin",
    "Niger", "Mauritanie", "Mauritania", "Gambia", "Gambie",
    "Sierra Leone", "Liberia", "Ghana",
]


class UNGMScraper(BaseScraper):
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
        delai    = src.get("delai_entre_requetes", 3)

        # Essai Playwright (UNGM nécessite souvent JS)
        items = list(self._scrape_playwright(base_url))
        if items:
            yield from items
            return

        # Fallback static
        yield from self._scrape_static(base_url, delai)

    def _scrape_playwright(self, base_url: str) -> Generator[dict, None, None]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            from bs4 import BeautifulSoup

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_extra_http_headers({
                    "User-Agent": self.config["scraping"]["user_agent"],
                })

                url = f"{base_url}/Public/Notice"
                try:
                    page.goto(url, timeout=25000, wait_until="networkidle")
                    try:
                        page.wait_for_selector("table, .notice-list, #tblNotices", timeout=10000)
                    except PWTimeout:
                        pass

                    p = 1
                    while p <= 5:
                        html = page.content()
                        soup = BeautifulSoup(html, "html.parser")

                        rows = (
                            soup.select("table#tblNotices tbody tr") or
                            soup.select("table tbody tr") or
                            soup.select(".notice-item")
                        )

                        if not rows:
                            break

                        logger.info(f"UNGM Playwright page {p}: {len(rows)} notices")

                        for row in rows:
                            item = self._parse_ungm_row(row, base_url)
                            if item:
                                yield item

                        # Pagination
                        next_btn = page.query_selector("a[rel='next'], .pagination .next:not(.disabled), [aria-label='Next']")
                        if not next_btn:
                            break
                        next_btn.click()
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except PWTimeout:
                            pass
                        p += 1

                except PWTimeout:
                    logger.debug(f"UNGM Playwright timeout")

                browser.close()

        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"UNGM Playwright: {e}")

    def _scrape_static(self, base_url: str, delai: float) -> Generator[dict, None, None]:
        page = 1
        while page <= 10:
            url = f"{base_url}/Public/Notice?page={page}"
            s = self.soup(url)
            if not s:
                break

            rows = (
                s.select("table#tblNotices tbody tr") or
                s.select(".notice-item") or
                s.select("tr[data-noticeid]")
            )
            if not rows:
                break

            logger.info(f"UNGM static page {page}: {len(rows)}")

            for row in rows:
                item = self._parse_ungm_row(row, base_url)
                if item:
                    yield item
                self.sleep(0.3)

            next_btn = s.select_one("a[rel='next'], .pagination .next:not(.disabled)")
            if not next_btn:
                break
            page += 1
            self.sleep(delai)

    def _parse_ungm_row(self, row, base_url: str) -> dict | None:
        try:
            text  = row.get_text(separator=" ", strip=True)
            if not text:
                return None

            cells = row.find_all("td")
            link  = row.find("a")
            objet = link.get_text(strip=True) if link else (cells[1].get_text(strip=True) if len(cells) > 1 else text[:200])

            href   = link.get("href", "") if link else ""
            url_ao = href if href.startswith("http") else f"{base_url}{href}"

            # Agence
            entite = ""
            for code, nom in _AGENCES_ONU.items():
                if code in text:
                    entite = nom
                    break

            # Pays
            pays = "Multi-pays"
            for p in _PAYS_AFRIQUE_OUEST:
                if p.lower() in text.lower():
                    pays = p if p != "Senegal" else "Sénégal"
                    pays = pays if p != "Ivory Coast" else "Côte d'Ivoire"
                    break

            date_pub   = _extract_date(text, 0)
            date_limit = _extract_date(text, 1)
            jours = max(0, (date_limit - datetime.utcnow()).days) if date_limit else None

            ref = cells[0].get_text(strip=True) if cells else f"UNGM_{hash(objet) & 0xFFFFFF:06X}"
            if not ref:
                ref = f"UNGM_{hash(objet) & 0xFFFFFF:06X}"

            return {
                "source":           _SOURCE_NOM,
                "date_publication": date_pub or datetime.utcnow(),
                "date_limite":      date_limit,
                "jours_restants":   jours,
                "reference":        ref,
                "objet":            objet,
                "entite":           entite,
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
            logger.debug(f"UNGM parse: {e}")
            return None

    def save_item(self, item: dict) -> bool:
        return upsert_ao(self.session_db, item)


def run(config: dict | None = None) -> int:
    return UNGMScraper(config).run()
