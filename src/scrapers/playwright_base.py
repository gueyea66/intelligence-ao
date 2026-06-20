"""
Base Playwright pour scrapers nécessitant un vrai browser.
Utilise le profil Chrome de l'utilisateur pour les sites nécessitant une auth.
"""
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CHROME_PROFILE = r"C:\Users\Abdou\AppData\Local\Google\Chrome\User Data"
CHROME_EXE     = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def get_pw_page(playwright, use_profile: bool = False, headless: bool = True):
    """
    Retourne (browser, context, page) Playwright.
    use_profile=True : utilise le profil Chrome existant (conserve les sessions FB, etc.)
    """
    if use_profile:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=CHROME_PROFILE,
            channel="chrome",
            headless=False,  # profil existant → non-headless obligatoire
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            ignore_https_errors=True,
        )
        page = context.new_page()
        return None, context, page
    else:
        browser = playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="fr-FR",
        )
        page = context.new_page()
        return browser, context, page


def scroll_to_bottom(page, max_scrolls: int = 5, pause: float = 1.5):
    """Scroll progressif pour charger le lazy-load."""
    for _ in range(max_scrolls):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(pause)
