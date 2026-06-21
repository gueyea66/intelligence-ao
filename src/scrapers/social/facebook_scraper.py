"""
Scraper Facebook — pages publiques et groupes ouverts (Afrique de l'Ouest, commerce).
Approche sans Graph API : scraping HTML via requests + BeautifulSoup sur pages publiques.
Les groupes Facebook privés ne sont PAS accessibles — uniquement pages publiques indexées.
"""
import os
import re
import time
import hashlib
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Pages publiques Facebook — commerce Afrique de l'Ouest
PUBLIC_PAGES = [
    "CoinAfriqueOfficiel",
    "JotayDakar",
    "marcheSenegal",
    "VenteAchatDakar",
    "ElectroniqueDakar",
    "CommerceAbidjanCI",
    "ImportExportAfriqueOuest",
]

# Groupes Facebook publics — accès en lecture via URL publique
PUBLIC_GROUPS = [
    # Ajoutez ici les IDs de groupes publics (ex: "1234567890")
    # Accessible via facebook.com/groups/{id} si le groupe est public
]


def scrape_facebook_page_posts(page_name: str, max_posts: int = 50) -> list[dict]:
    """
    Scrape les publications récentes d'une page Facebook publique.
    Utilise mbasic.facebook.com (version simplifiée sans JS).
    """
    posts = []
    url = f"https://mbasic.facebook.com/{page_name}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"HTTP {resp.status_code} pour {page_name}")
            return posts

        soup = BeautifulSoup(resp.text, "html.parser")

        # mbasic.facebook.com structure : articles dans des divs avec data-ft
        articles = soup.find_all("div", attrs={"data-ft": True})[:max_posts]

        for article in articles:
            # Extraire texte principal
            text_div = article.find("div", class_=re.compile(r"story_body|_5pbx|_2vxa"))
            if not text_div:
                text_div = article
            text = text_div.get_text(separator=" ", strip=True)

            if len(text) < 15:
                continue

            # Hash stable pour déduplication
            msg_hash = hashlib.sha256(f"{page_name}:{text[:100]}".encode()).hexdigest()[:16]

            posts.append({
                "plateforme": "facebook",
                "canal": page_name,
                "canal_id": page_name,
                "message_id": msg_hash,
                "texte_brut": text[:2000],
                "date_publication": datetime.utcnow(),  # mbasic cache la date exacte
                "auteur_hash": hashlib.sha256(page_name.encode()).hexdigest(),
            })

        logger.info(f"Facebook page {page_name}: {len(posts)} posts")

    except Exception as e:
        logger.warning(f"Erreur page {page_name}: {e}")

    time.sleep(2)  # politesse
    return posts


def scrape_facebook_search(query: str, max_results: int = 30) -> list[dict]:
    """
    Recherche Facebook publique via mbasic (résultats de search).
    Utile pour capturer des discussions autour d'un sujet (ex: "prix riz Dakar").
    """
    posts = []
    url = f"https://mbasic.facebook.com/search/posts/?q={requests.utils.quote(query)}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return posts

        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.find_all("div", attrs={"data-ft": True})[:max_results]

        for r in results:
            text = r.get_text(separator=" ", strip=True)
            if len(text) < 20:
                continue

            msg_hash = hashlib.sha256(f"search:{query}:{text[:80]}".encode()).hexdigest()[:16]
            posts.append({
                "plateforme": "facebook",
                "canal": f"search:{query}",
                "canal_id": f"search:{query}",
                "message_id": msg_hash,
                "texte_brut": text[:2000],
                "date_publication": datetime.utcnow(),
                "auteur_hash": "search_result",
            })

    except Exception as e:
        logger.warning(f"Erreur recherche '{query}': {e}")

    time.sleep(2)
    return posts


# Requêtes de recherche pour capter les discussions marché informel
SEARCH_QUERIES = [
    "prix riz Dakar",
    "vente telephone Dakar",
    "prix tissu wax Sénégal",
    "commerce import export Abidjan",
    "arnaque vente en ligne Afrique",
    "marché informel Dakar",
    "grossiste Sandaga",
    "prix FCFA electronics",
    "achat groupé Dakar",
    "livraison Sénégal",
]


def scrape_and_store(db_session):
    """Scrape Facebook + analyse NLP + stocke en DB."""
    from src.analytics.nlp_engine import analyze_message
    from src.database.social_models import DiscussionSociale
    from sqlalchemy.exc import IntegrityError

    all_messages = []

    # Pages publiques
    for page in PUBLIC_PAGES:
        msgs = scrape_facebook_page_posts(page)
        all_messages.extend(msgs)

    # Recherches thématiques
    for query in SEARCH_QUERIES:
        msgs = scrape_facebook_search(query, max_results=20)
        all_messages.extend(msgs)

    logger.info(f"Total Facebook: {len(all_messages)} messages")

    inserted = 0
    for msg in all_messages:
        try:
            nlp = analyze_message(msg["texte_brut"])
            record = DiscussionSociale(
                plateforme=msg["plateforme"],
                canal=msg["canal"],
                canal_id=msg["canal_id"],
                message_id=msg["message_id"],
                texte_brut=msg["texte_brut"],
                date_publication=msg["date_publication"],
                auteur_hash=msg["auteur_hash"],
                langue=nlp["langue"],
                sentiment=nlp["sentiment"],
                score_sentiment=nlp["score_sentiment"],
                topics=nlp["topics"],
                pain_points=nlp["pain_points"],
                prix_mentionnes=nlp["prix_mentionnes"],
                type_message=nlp["type_message"],
                contient_prix=nlp["contient_prix"],
                contient_contact=nlp["contient_contact"],
                traite=True,
            )
            db_session.add(record)
            db_session.commit()
            inserted += 1
        except IntegrityError:
            db_session.rollback()
        except Exception as e:
            db_session.rollback()
            logger.warning(f"Erreur: {e}")

    return inserted
