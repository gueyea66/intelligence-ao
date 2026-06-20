"""
Scraper Jumia Sénégal — collecte catalogue produits.
Toutes les URLs et paramètres viennent de config.yaml.
"""
import time
import logging
from datetime import datetime
from typing import Generator

import requests
from bs4 import BeautifulSoup

from src.database.models import Produit, LogCollecte, get_session
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)

_SOURCE_NOM = "Jumia Sénégal"


def _source_config(config: dict) -> dict:
    for src in config["sources"]["ecommerce"]:
        if src["nom"] == _SOURCE_NOM:
            return src
    raise ValueError(f"Source '{_SOURCE_NOM}' introuvable dans config.yaml")


def _headers(config: dict) -> dict:
    return {"User-Agent": config["scraping"]["user_agent"]}


def _get(url: str, config: dict) -> requests.Response | None:
    """GET avec retry configurable."""
    timeout = config["scraping"]["timeout"]
    max_retries = config["scraping"]["max_retries"]
    delai_retry = config["scraping"]["delai_retry"]

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=_headers(config), timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.warning(f"Tentative {attempt}/{max_retries} échouée pour {url}: {e}")
            if attempt < max_retries:
                time.sleep(delai_retry)
    return None


def _parse_produit(card, source_url: str, pays: str) -> dict | None:
    """Extrait les champs d'un article Jumia depuis la carte HTML."""
    try:
        nom_el     = card.select_one("[class*='name']")
        prix_el    = card.select_one("[class*='prc']")
        barre_el   = card.select_one("[class*='old']")
        img_el     = card.select_one("img")
        link_el    = card.select_one("a")

        if not nom_el or not prix_el:
            return None

        nom_complet = nom_el.get_text(strip=True)
        # Sépare marque et modèle heuristiquement (premier mot = marque)
        parts = nom_complet.split(" ", 1)
        marque = parts[0] if len(parts) > 1 else ""
        modele = parts[1] if len(parts) > 1 else nom_complet

        prix_text = prix_el.get_text(strip=True).replace("\xa0", "").replace(",", "").replace("F", "").strip()
        try:
            prix = float("".join(c for c in prix_text if c.isdigit() or c == "."))
        except ValueError:
            prix = None

        prix_barre = None
        if barre_el:
            barre_text = barre_el.get_text(strip=True).replace("\xa0", "").replace(",", "").replace("F", "").strip()
            try:
                prix_barre = float("".join(c for c in barre_text if c.isdigit() or c == "."))
            except ValueError:
                pass

        url_produit = ""
        if link_el and link_el.get("href"):
            href = link_el["href"]
            url_produit = href if href.startswith("http") else f"https://www.jumia.sn{href}"

        return {
            "marque": marque,
            "modele": modele,
            "description": nom_complet,
            "prix_actuel": prix,
            "prix_barre": prix_barre,
            "promotion": prix_barre is not None and prix_barre > (prix or 0),
            "devise": "XOF",
            "pays": pays,
            "url_source": url_produit or source_url,
            "disponibilite": "En stock",
        }
    except Exception as e:
        logger.debug(f"Erreur parsing carte: {e}")
        return None


def _scrape_page(url: str, config: dict, categorie_1: str = "", categorie_2: str = "") -> Generator[dict, None, None]:
    """Scrape une page de listing Jumia, yield les produits parsés."""
    resp = _get(url, config)
    if not resp:
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("article.prd")

    if not cards:
        logger.debug(f"Aucune carte trouvée sur {url}")
        return

    for card in cards:
        data = _parse_produit(card, url, pays="Sénégal")
        if data:
            data["categorie_1"] = categorie_1
            data["categorie_2"] = categorie_2
            yield data


def _get_categories(config: dict, src_config: dict) -> list[dict]:
    """
    Récupère les catégories Jumia dynamiquement depuis la page d'accueil.
    Retourne une liste de {nom, url}.
    """
    base_url = src_config["url"]
    resp = _get(base_url, config)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    categories = []

    for link in soup.select("nav a[href*='/catalog/']"):
        href = link.get("href", "")
        nom  = link.get_text(strip=True)
        if href and nom:
            url = href if href.startswith("http") else f"https://www.jumia.sn{href}"
            categories.append({"nom": nom, "url": url})

    # Dédoublonnage par URL
    seen = set()
    unique = []
    for cat in categories:
        if cat["url"] not in seen:
            seen.add(cat["url"])
            unique.append(cat)

    logger.info(f"{len(unique)} catégories trouvées sur Jumia")
    return unique


def run(config: dict | None = None) -> int:
    """
    Point d'entrée principal — lance le scraping Jumia complet.
    Retourne le nombre de produits insérés.
    """
    if config is None:
        config = load_config()

    src_config = _source_config(config)
    if not src_config.get("actif", False):
        logger.info(f"Source '{_SOURCE_NOM}' désactivée dans config.yaml")
        return 0

    delai = src_config.get("delai_entre_requetes", 2)
    max_pages = src_config.get("max_pages", 50)

    session = get_session(config)
    log = LogCollecte(
        source_nom=_SOURCE_NOM,
        source_type="ecommerce",
        statut="en_cours",
    )
    session.add(log)
    session.commit()

    nb_inseres = 0
    nb_erreurs = 0

    try:
        categories = _get_categories(config, src_config)

        if not categories:
            # Fallback : scrape la page principale
            categories = [{"nom": "Général", "url": src_config["url"]}]

        for cat in categories:
            logger.info(f"Scraping catégorie: {cat['nom']}")
            page = 1

            while page <= max_pages:
                sep = "&" if "?" in cat["url"] else "?"
                page_url = f"{cat['url']}{sep}page={page}"
                produits = list(_scrape_page(page_url, config, categorie_1=cat["nom"]))

                if not produits:
                    break  # Plus de résultats

                for p in produits:
                    try:
                        produit = Produit(
                            source=_SOURCE_NOM,
                            date_collecte=datetime.utcnow(),
                            categorie_1=p.get("categorie_1", ""),
                            categorie_2=p.get("categorie_2", ""),
                            marque=p.get("marque", ""),
                            modele=p.get("modele", ""),
                            description=p.get("description", ""),
                            prix_actuel=p.get("prix_actuel"),
                            prix_barre=p.get("prix_barre"),
                            promotion=p.get("promotion", False),
                            devise=p.get("devise", "XOF"),
                            pays=p.get("pays", "Sénégal"),
                            url_source=p.get("url_source", ""),
                            disponibilite=p.get("disponibilite", ""),
                        )
                        session.add(produit)
                        nb_inseres += 1
                    except Exception as e:
                        logger.warning(f"Erreur insertion produit: {e}")
                        nb_erreurs += 1

                session.commit()
                logger.info(f"  Page {page}: {len(produits)} produits — total: {nb_inseres}")

                page += 1
                time.sleep(delai)

        log.statut = "succes"
        log.nb_items = nb_inseres

    except Exception as e:
        logger.error(f"Erreur scraping Jumia: {e}", exc_info=True)
        log.statut = "erreur"
        log.erreur_detail = str(e)

    finally:
        log.date_fin = datetime.utcnow()
        session.commit()
        session.close()

    logger.info(f"Jumia terminé — {nb_inseres} insérés, {nb_erreurs} erreurs")
    return nb_inseres


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
