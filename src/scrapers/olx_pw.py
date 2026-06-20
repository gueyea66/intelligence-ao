"""
OLX Sénégal — scraper Playwright (contourne 403).
"""
import logging
import re
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from src.database.db import upsert_informel
from src.database.models import get_session, get_engine, Base
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)
_SOURCE = "OLX Sénégal"

_CATEGORIES_OLX = [
    "telephonie",
    "electronique",
    "informatique",
    "maison-et-living",
    "mode-et-beaute",
    "materiaux-de-construction",
    "services",
    "equipement-professionnel",
]

_BASE = "https://sn.olx.com"


_CHROME_PROFILE = r"C:\Users\Abdou\AppData\Local\Google\Chrome\User Data"


def _kill_chrome():
    import subprocess
    subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
    import time; time.sleep(2)


def run(config=None) -> int:
    if config is None:
        config = load_config()

    Base.metadata.create_all(get_engine(config))
    session = get_session(config)
    nb_ok = 0

    _kill_chrome()

    with sync_playwright() as pw:
        # Utiliser profil Chrome pour contourner détection anti-bot
        try:
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=_CHROME_PROFILE,
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                locale="fr-SN",
                viewport={"width": 1366, "height": 768},
            )
            use_profile = True
        except Exception as e:
            logger.warning(f"OLX: profil Chrome indispo ({e}), fallback headless")
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                locale="fr-SN",
                viewport={"width": 1366, "height": 768},
            )
            use_profile = False

        page = ctx.new_page()

        # Accepter cookies si banner présent
        try:
            page.goto(_BASE, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            for btn_text in ["Accepter", "Accept", "J'accepte", "OK"]:
                btn = page.query_selector(f"button:has-text('{btn_text}')")
                if btn:
                    btn.click()
                    break
        except Exception:
            pass

        for cat in _CATEGORIES_OLX:
            for p in range(1, 4):
                url = f"{_BASE}/{cat}/?page={p}"
                try:
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)

                    # OLX sélecteurs typiques
                    cards = (
                        page.query_selector_all("[data-aut-id='itemBox']") or
                        page.query_selector_all("li[class*='EIR5N']") or
                        page.query_selector_all("article") or
                        page.query_selector_all("[class*='item--']")
                    )
                    if not cards:
                        break

                    for card in cards:
                        try:
                            titre_el = card.query_selector(
                                "[data-aut-id='itemTitle'], h2, h3, [class*='title']"
                            )
                            titre = titre_el.inner_text().strip() if titre_el else ""
                            if not titre or len(titre) < 4:
                                continue

                            prix_el = card.query_selector(
                                "[data-aut-id='itemPrice'], [class*='price'], [class*='Price']"
                            )
                            prix_txt = prix_el.inner_text() if prix_el else ""
                            m = re.search(r"[\d\s]{3,}", prix_txt)
                            prix = float(re.sub(r"\s", "", m.group())) if m else None

                            link = card.query_selector("a")
                            href = link.get_attribute("href") if link else ""
                            url_ann = href if (href or "").startswith("http") else f"{_BASE}{href}"

                            item = {
                                "source":             _SOURCE,
                                "date_collecte":      datetime.utcnow(),
                                "type":               "offre",
                                "produit":            titre[:200],
                                "marque":             "",
                                "prix_unitaire":      prix,
                                "devise":             "XOF",
                                "vendeur_zone":       "Sénégal",
                                "contact_disponible": True,
                                "url_annonce":        url_ann,
                                "notes_terrain":      cat,
                            }
                            if upsert_informel(session, item):
                                nb_ok += 1
                        except Exception:
                            pass

                    logger.info(f"OLX {cat} p{p}: {nb_ok} total")

                except PWTimeout:
                    logger.warning(f"OLX timeout: {url}")
                    break
                except Exception as e:
                    logger.warning(f"OLX {cat} p{p}: {e}")
                    break

        ctx.close()
        if not use_profile:
            browser.close()

    session.close()
    logger.info(f"OLX terminé: {nb_ok} annonces")
    return nb_ok
