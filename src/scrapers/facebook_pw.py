"""
Facebook Marketplace Dakar — scraper Playwright avec profil Chrome existant.
Utilise la session FB déjà connectée dans Chrome (pas de re-login).

IMPORTANT : Chrome doit être fermé avant d'utiliser ce scraper
(Playwright et Chrome ne peuvent pas partager le même profil simultanément).
"""
import logging
import re
import time
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from src.database.db import upsert_informel
from src.database.models import get_session, get_engine, Base
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)
_SOURCE = "Facebook Marketplace"

CHROME_PROFILE = r"C:\Users\Abdou\AppData\Local\Google\Chrome\User Data"

_CATEGORIES_FB = [
    "electronics",
    "phones",
    "home-garden",
    "clothing",
    "vehicles",
    "home-appliances",
    "tools-equipment",
    "sporting-goods",
]

_BASE_URL = "https://www.facebook.com/marketplace/dakar"


def _parse_prix(txt: str):
    m = re.search(r"([\d\s]{3,})\s*(F\s*CFA|FCFA|CFA|XOF|€|\$)?", txt, re.IGNORECASE)
    if m:
        try:
            return float(re.sub(r"\s", "", m.group(1)))
        except ValueError:
            pass
    return None


def _kill_chrome():
    """Ferme Chrome si ouvert pour libérer le profil."""
    import subprocess
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
        time.sleep(2)
    except Exception:
        pass


def run(config=None) -> int:
    if config is None:
        config = load_config()

    Base.metadata.create_all(get_engine(config))
    session = get_session(config)
    nb_ok = 0

    _kill_chrome()  # Libérer le profil

    with sync_playwright() as pw:
        try:
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=CHROME_PROFILE,
                channel="chrome",
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--profile-directory=Default",
                ],
                ignore_https_errors=True,
                viewport={"width": 1366, "height": 768},
            )
        except Exception as e:
            logger.error(f"FB: impossible d'ouvrir le profil Chrome: {e}")
            logger.info("FB: tentative en mode incognito sans profil...")
            # Fallback: browser normal sans profil
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
            )

        page = ctx.new_page()

        # Vérifier si connecté à FB
        try:
            page.goto("https://www.facebook.com", timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            is_logged_in = page.query_selector("[aria-label='Facebook'], [data-pagelet='ProfileDropdown']") is not None
            if not is_logged_in:
                logger.warning("FB: non connecté — le scraping Marketplace sera limité")
        except Exception:
            is_logged_in = False

        for cat in _CATEGORIES_FB:
            url = f"{_BASE_URL}/{cat}?sortBy=creation_time_descend"
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Scroll pour charger les annonces
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    page.wait_for_timeout(1500)

                cards = (
                    page.query_selector_all("[class*='x9f619']") or
                    page.query_selector_all("div[class*='marketplace'] a") or
                    page.query_selector_all("a[href*='/marketplace/item/']")
                )

                for card in cards[:30]:  # max 30 par catégorie
                    try:
                        titre_el = card.query_selector("span[class*='x1lliihq'], h2, span")
                        titre = titre_el.inner_text().strip() if titre_el else card.inner_text()[:80].strip()
                        if not titre or len(titre) < 3:
                            continue

                        prix_el = card.query_selector("span[class*='price'], [aria-label*='CFA'], [aria-label*='FCFA']")
                        prix = _parse_prix(prix_el.inner_text()) if prix_el else None

                        href = card.get_attribute("href") or ""
                        if "/marketplace/item/" not in href:
                            link = card.query_selector("a[href*='/marketplace/item/']")
                            href = link.get_attribute("href") if link else ""
                        url_ann = f"https://www.facebook.com{href}" if href.startswith("/") else href

                        item = {
                            "source":             _SOURCE,
                            "date_collecte":      datetime.utcnow(),
                            "type":               "offre",
                            "produit":            titre[:200],
                            "marque":             "",
                            "prix_unitaire":      prix,
                            "devise":             "XOF",
                            "vendeur_zone":       "Dakar",
                            "contact_disponible": is_logged_in,
                            "url_annonce":        url_ann,
                            "notes_terrain":      f"fb_{cat}",
                        }
                        if upsert_informel(session, item):
                            nb_ok += 1
                    except Exception:
                        pass

                logger.info(f"FB Marketplace {cat}: {nb_ok} total")

            except PWTimeout:
                logger.warning(f"FB timeout: {url}")
            except Exception as e:
                logger.warning(f"FB {cat}: {e}")

        try:
            ctx.close()
        except Exception:
            pass

    session.close()
    logger.info(f"Facebook Marketplace terminé: {nb_ok} annonces")
    return nb_ok
