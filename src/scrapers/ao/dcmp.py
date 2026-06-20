"""
Scanner DCMP Sénégal — Direction Centrale des Marchés Publics.
Utilise Playwright (JS dynamique) avec fallback requests/BS4.
URL : https://www.dcmp.sn
"""
import re
import logging
from datetime import datetime
from typing import Generator

from src.scrapers.base_scraper import BaseScraper
from src.database.db import upsert_ao

logger = logging.getLogger(__name__)
_SOURCE_NOM = "DCMP Sénégal"


class DCMPScraper(BaseScraper):
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
            logger.info(f"{_SOURCE_NOM} désactivé")
            return

        base_url = src["url"]

        # Essai 1 : Playwright (JS)
        items = list(self._scrape_playwright(base_url))
        if items:
            yield from items
            return

        # Fallback : requests static
        yield from self._scrape_static(base_url)

    def _scrape_playwright(self, base_url: str) -> Generator[dict, None, None]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

            listing_paths = [
                "/appels-offres",
                "/avis-appel-offres",
                "/marches-publics",
                "/publication",
            ]

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_extra_http_headers({
                    "User-Agent": self.config["scraping"]["user_agent"],
                    "Accept-Language": "fr-FR,fr;q=0.9",
                })

                found = False
                for path in listing_paths:
                    url = f"{base_url}{path}"
                    try:
                        page.goto(url, timeout=20000, wait_until="networkidle")
                        # Attendre chargement tableau
                        try:
                            page.wait_for_selector("table, .ao-list, .listing, article", timeout=8000)
                        except PWTimeout:
                            pass

                        html = page.content()
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html, "html.parser")

                        rows = (
                            soup.select("table tbody tr") or
                            soup.select(".ao-item") or
                            soup.select("article") or
                            soup.select(".listing-row")
                        )

                        if rows:
                            logger.info(f"DCMP Playwright: {len(rows)} entrées sur {url}")
                            for row in rows:
                                item = _parse_row(row, base_url)
                                if item:
                                    yield item
                            found = True
                            break

                    except PWTimeout:
                        logger.debug(f"DCMP Playwright timeout: {url}")
                    except Exception as e:
                        logger.debug(f"DCMP Playwright error {url}: {e}")

                browser.close()

                if not found:
                    logger.info("DCMP Playwright: aucun résultat, fallback static")

        except ImportError:
            logger.warning("Playwright non installé")
        except Exception as e:
            logger.warning(f"DCMP Playwright global error: {e}")

    def _scrape_static(self, base_url: str) -> Generator[dict, None, None]:
        listing_paths = [
            "/appels-offres",
            "/avis-appel-offres",
            "/marches-publics",
            "/publication-ao",
        ]
        for path in listing_paths:
            url = f"{base_url}{path}"
            s = self.soup(url)
            if not s:
                continue

            rows = (
                s.select("table tbody tr") or
                s.select(".ao-item") or
                s.select("article") or
                s.select(".listing-item")
            )
            if not rows:
                continue

            logger.info(f"DCMP static: {len(rows)} entrées sur {url}")
            for row in rows:
                item = _parse_row(row, base_url)
                if item:
                    yield item
                    self.sleep(0.3)
            break

    def save_item(self, item: dict) -> bool:
        return upsert_ao(self.session_db, item)


# ── Helpers partagés ─────────────────────────────────────────────────────────

_DATE_PATTERNS = [
    r"(\d{2})[/\-\.](\d{2})[/\-\.](\d{4})",
    r"(\d{4})[/\-\.](\d{2})[/\-\.](\d{2})",
]

def _extract_date(text: str, offset: int = 0) -> datetime | None:
    matches = []
    for pat in _DATE_PATTERNS:
        matches.extend(re.findall(pat, text))
    if len(matches) > offset:
        g = matches[offset]
        try:
            if len(g[0]) == 4:
                return datetime(int(g[0]), int(g[1]), int(g[2]))
            return datetime(int(g[2]), int(g[1]), int(g[0]))
        except ValueError:
            return None
    return None


def _extract_budget(text: str) -> float | None:
    m = re.search(r"([\d\s]{5,})\s*(F\s*CFA|XOF|FCFA|francs?)", text, re.IGNORECASE)
    if m:
        try:
            return float(re.sub(r"\s", "", m.group(1)))
        except ValueError:
            pass
    return None


def _extract_entite(text: str) -> str:
    keywords = ["Ministère", "Direction", "Agence", "Office", "Autorité",
                "Société nationale", "Université", "Hôpital", "Centre"]
    for kw in keywords:
        idx = text.find(kw)
        if idx >= 0:
            return text[idx:idx+80].split(".")[0].strip()
    return ""


_CATEGORIES_KEYWORDS = {
    "Informatique": ["informatique", "ordinateur", "serveur", "réseau", "logiciel", "it", "numérique"],
    "Travaux BTP":  ["travaux", "construction", "réhabilitation", "bâtiment", "route", "pont", "génie civil"],
    "Fournitures":  ["fourniture", "matériel", "équipement", "mobilier", "bureau"],
    "Services":     ["service", "prestation", "conseil", "formation", "audit", "étude", "consultant"],
    "Santé":        ["médicament", "santé", "médical", "hôpital", "vaccin", "pharmaceutique"],
    "Alimentation": ["alimentaire", "denrée", "vivres", "nutrition", "nourriture"],
    "Transport":    ["véhicule", "transport", "logistique", "camion", "flotte"],
    "Énergie":      ["énergie", "électricité", "solaire", "générateur", "panneau"],
}

def _guess_categorie(objet: str) -> str:
    objet_low = objet.lower()
    for cat, keywords in _CATEGORIES_KEYWORDS.items():
        if any(kw in objet_low for kw in keywords):
            return cat
    return "Autre"


def _parse_row(row, base_url: str) -> dict | None:
    try:
        text = row.get_text(separator=" ", strip=True)
        if not text or len(text) < 10:
            return None

        link   = row.find("a")
        url_ao = ""
        if link and link.get("href"):
            href   = link["href"]
            url_ao = href if href.startswith("http") else f"{base_url}{href}"

        objet = link.get_text(strip=True) if link else text[:200]

        date_pub   = _extract_date(text, 0)
        date_limit = _extract_date(text, 1)

        ref_match = re.search(r"(DCMP[/-]\d{4}[/-][A-Z0-9/-]+)", text)
        reference = ref_match.group(1) if ref_match else f"DCMP_{hash(objet) & 0xFFFFFF:06X}"

        budget = _extract_budget(text)

        jours = None
        if date_limit:
            jours = max(0, (date_limit - datetime.utcnow()).days)

        return {
            "source":           _SOURCE_NOM,
            "date_publication": date_pub or datetime.utcnow(),
            "date_limite":      date_limit,
            "jours_restants":   jours,
            "reference":        reference,
            "objet":            objet,
            "entite":           _extract_entite(text),
            "pays":             "Sénégal",
            "ville":            "Dakar",
            "budget_estime":    budget,
            "devise":           "XOF",
            "categorie":        _guess_categorie(objet),
            "url_source":       url_ao,
            "statut":           "nouveau",
            "date_collecte":    datetime.utcnow(),
        }
    except Exception as e:
        logger.debug(f"DCMP parse error: {e}")
        return None


def run(config: dict | None = None) -> int:
    return DCMPScraper(config).run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
