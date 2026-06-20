"""
CoinAfrique Sénégal — scraper Playwright (contourne anti-bot).
"""
import logging
import re
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from src.database.db import upsert_informel
from src.database.models import get_session, get_engine, Base
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)
_SOURCE = "CoinAfrique"

_CATEGORIES = [
    "telephones",
    "electronique",
    "electromenager",
    "vetements-femme",
    "vetements-homme",
    "informatique",
    "meubles-et-decoration",
    "materiaux-et-outillage",
    "alimentation",
    "services",
]

_BASE = "https://sn.coinafrique.com"


def _parse_prix(txt: str):
    m = re.search(r"([\d\s]{3,})\s*(F\s*CFA|FCFA|CFA)?", txt, re.IGNORECASE)
    if m:
        try:
            return float(re.sub(r"\s", "", m.group(1)))
        except ValueError:
            pass
    return None


def run(config=None) -> int:
    if config is None:
        config = load_config()

    Base.metadata.create_all(get_engine(config))
    session = get_session(config)
    nb_ok = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        for cat in _CATEGORIES:
            for p in range(1, 4):  # 3 pages par catégorie
                url = f"{_BASE}/categorie/{cat}?page={p}"
                try:
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

                    cards = page.query_selector_all(".card, [class*='ad-card'], article, .col-item")
                    if not cards:
                        break

                    for card in cards:
                        try:
                            titre_el = card.query_selector("h3, h2, .name, [class*='name'], p.title")
                            titre = titre_el.inner_text().strip() if titre_el else ""
                            if not titre or len(titre) < 4:
                                continue

                            prix_el = card.query_selector(".price, [class*='price'], .prix")
                            prix = _parse_prix(prix_el.inner_text()) if prix_el else None

                            link = card.query_selector("a")
                            href = link.get_attribute("href") if link else ""
                            url_ann = href if (href or "").startswith("http") else f"{_BASE}{href}"

                            loc_el = card.query_selector("[class*='location'], [class*='city'], .location")
                            zone = loc_el.inner_text().strip()[:50] if loc_el else "Sénégal"

                            item = {
                                "source":             _SOURCE,
                                "date_collecte":      datetime.utcnow(),
                                "type":               "offre",
                                "produit":            titre[:200],
                                "marque":             "",
                                "prix_unitaire":      prix,
                                "devise":             "XOF",
                                "vendeur_zone":       zone,
                                "contact_disponible": True,
                                "url_annonce":        url_ann,
                                "notes_terrain":      cat,
                            }
                            if upsert_informel(session, item):
                                nb_ok += 1
                        except Exception:
                            pass

                    logger.info(f"CoinAfrique {cat} p{p}: {nb_ok} total")

                except PWTimeout:
                    logger.warning(f"CoinAfrique timeout: {url}")
                    break
                except Exception as e:
                    logger.warning(f"CoinAfrique {cat} p{p}: {e}")
                    break

        ctx.close()
        browser.close()

    session.close()
    logger.info(f"CoinAfrique terminé: {nb_ok} annonces")
    return nb_ok
