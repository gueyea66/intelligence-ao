"""
Classe abstraite commune à tous les scrapers.
Gère : retry, rate limiting, logging, persistance en base.
"""
import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generator

import requests
from bs4 import BeautifulSoup

from src.database.models import LogCollecte, get_session
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Hérite de cette classe pour chaque source.
    Implémenter : source_nom, source_type, scrape_items().
    """

    source_nom: str = ""
    source_type: str = "ecommerce"   # ecommerce | ao | informel | macro

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.session_db = get_session(self.config)
        self._scraping_cfg = self.config.get("scraping", {})
        self._log = None

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    @property
    def _headers(self) -> dict:
        return {"User-Agent": self._scraping_cfg.get("user_agent", "Mozilla/5.0")}

    def get(self, url: str) -> requests.Response | None:
        timeout    = self._scraping_cfg.get("timeout", 30)
        max_retries = self._scraping_cfg.get("max_retries", 3)
        delai_retry = self._scraping_cfg.get("delai_retry", 10)

        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, headers=self._headers, timeout=timeout)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                logger.warning(f"[{self.source_nom}] {attempt}/{max_retries} — {url}: {e}")
                if attempt < max_retries:
                    time.sleep(delai_retry)
        return None

    def soup(self, url: str) -> BeautifulSoup | None:
        resp = self.get(url)
        if resp:
            return BeautifulSoup(resp.text, "html.parser")
        return None

    def sleep(self, seconds: float | None = None):
        s = seconds or self._scraping_cfg.get("delai_entre_requetes", 2)
        time.sleep(s)

    # ── Interface à implémenter ───────────────────────────────────────────────

    @abstractmethod
    def scrape_items(self) -> Generator[dict, None, None]:
        """Yield des dicts bruts représentant chaque item collecté."""
        ...

    @abstractmethod
    def save_item(self, item: dict) -> bool:
        """Persiste un item en base. Retourne True si insertion réussie."""
        ...

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def run(self) -> int:
        """Lance le scraping complet avec logging en base. Retourne nb items."""
        logger.info(f"[{self.source_nom}] Démarrage")

        self._log = LogCollecte(
            source_nom=self.source_nom,
            source_type=self.source_type,
            statut="en_cours",
            date_debut=datetime.utcnow(),
        )
        self.session_db.add(self._log)
        self.session_db.commit()

        nb_ok = 0
        nb_err = 0

        try:
            for item in self.scrape_items():
                try:
                    if self.save_item(item):
                        nb_ok += 1
                except Exception as e:
                    logger.warning(f"[{self.source_nom}] Erreur save: {e}")
                    nb_err += 1

            self._log.statut = "succes"

        except Exception as e:
            logger.error(f"[{self.source_nom}] Erreur fatale: {e}", exc_info=True)
            self._log.statut = "erreur"
            self._log.erreur_detail = str(e)

        finally:
            self._log.date_fin = datetime.utcnow()
            self._log.nb_items = nb_ok
            self.session_db.commit()
            self.session_db.close()

        logger.info(f"[{self.source_nom}] Terminé — {nb_ok} OK / {nb_err} erreurs")
        return nb_ok
