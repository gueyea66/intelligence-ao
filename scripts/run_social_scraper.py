"""
Runner pour le scraping social intelligence.
Usage: python scripts/run_social_scraper.py [telegram|facebook|all]
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    logger.error("DATABASE_URL non défini")
    sys.exit(1)

from src.database.models import get_session
config = {"database": {"type": "postgresql", "postgresql_url": db_url}}
session = get_session(config)

# Créer la table si nécessaire
from sqlalchemy import text
try:
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS discussions_sociales (
            id SERIAL PRIMARY KEY,
            plateforme VARCHAR(50),
            canal VARCHAR(255),
            canal_id VARCHAR(255),
            message_id VARCHAR(255),
            texte_brut TEXT,
            langue VARCHAR(10),
            date_publication TIMESTAMP,
            date_collecte TIMESTAMP DEFAULT NOW(),
            auteur_hash VARCHAR(64),
            sentiment VARCHAR(20),
            score_sentiment FLOAT,
            topics JSONB,
            pain_points JSONB,
            prix_mentionnes JSONB,
            entites JSONB,
            mots_cles JSONB,
            type_message VARCHAR(50),
            categorie_produit VARCHAR(100),
            contient_prix BOOLEAN DEFAULT FALSE,
            contient_contact BOOLEAN DEFAULT FALSE,
            est_spam BOOLEAN DEFAULT FALSE,
            traite BOOLEAN DEFAULT FALSE,
            UNIQUE(plateforme, canal_id, message_id)
        )
    """))
    session.commit()
    logger.info("Table discussions_sociales OK")
except Exception as e:
    logger.warning(f"Table creation: {e}")
    session.rollback()

mode = sys.argv[1] if len(sys.argv) > 1 else "all"

if mode in ("telegram", "all"):
    logger.info("=== Scraping Telegram ===")
    try:
        from src.scrapers.social.telegram_scraper import scrape_and_store
        n = scrape_and_store(session)
        logger.info(f"Telegram: {n} messages insérés")
    except Exception as e:
        logger.error(f"Telegram erreur: {e}")

if mode in ("facebook", "all"):
    logger.info("=== Scraping Facebook ===")
    try:
        from src.scrapers.social.facebook_scraper import scrape_and_store
        n = scrape_and_store(session)
        logger.info(f"Facebook: {n} messages insérés")
    except Exception as e:
        logger.error(f"Facebook erreur: {e}")

session.close()
logger.info("Social scraping terminé")
