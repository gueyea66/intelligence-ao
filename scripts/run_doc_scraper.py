"""
Runner pour le scraping de documents institutionnels.
Usage: python scripts/run_doc_scraper.py
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    print("ERROR: DATABASE_URL non défini")
    sys.exit(1)

from src.database.models import get_session
from src.scrapers.documents.doc_scraper import scrape_and_store_documents

config = {"database": {"type": "postgresql", "postgresql_url": db_url}}
session = get_session(config)

inserted, updated = scrape_and_store_documents(session)
session.close()

print(f"Documents terminé: {inserted} insérés, {updated} mis à jour")
