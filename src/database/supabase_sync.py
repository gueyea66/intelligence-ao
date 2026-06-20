"""
Synchronisation vers Supabase via REST API (pas de psycopg2 requis).
Pousse les données locales SQLite vers Supabase PostgreSQL.

Variables d'environnement requises :
    SUPABASE_URL  = https://xxxxx.supabase.co
    SUPABASE_KEY  = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  (service_role key)
"""
import logging
import os
from datetime import datetime, date

import requests

from src.database.models import AppelOffre, ProduitInformel, Entreprise, get_session
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)


def _headers():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        raise ValueError("SUPABASE_URL et SUPABASE_KEY requis dans .env")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }, url


def _serialize(obj):
    """Convertit un objet SQLAlchemy en dict JSON-sérialisable."""
    if hasattr(obj, "__table__"):
        d = {}
        for col in obj.__table__.columns:
            val = getattr(obj, col.name)
            if isinstance(val, (datetime, date)):
                val = val.isoformat()
            d[col.name] = val
        return d
    return {}


def _upsert(table: str, rows: list, headers: dict, base_url: str) -> int:
    if not rows:
        return 0
    url = f"{base_url}/rest/v1/{table}"
    resp = requests.post(url, headers=headers, json=rows, timeout=30)
    if resp.status_code in (200, 201):
        return len(rows)
    logger.warning(f"Supabase {table}: HTTP {resp.status_code} — {resp.text[:200]}")
    return 0


def sync_aos(config=None, limit: int = 500) -> int:
    """Pousse les AOs récents vers Supabase."""
    headers, base_url = _headers()
    session = get_session(config or load_config())
    aos = session.query(AppelOffre).order_by(AppelOffre.id.desc()).limit(limit).all()
    rows = [_serialize(a) for a in aos]
    session.close()
    n = _upsert("appels_offres", rows, headers, base_url)
    logger.info(f"Supabase sync AOs: {n}/{len(rows)}")
    return n


def sync_informel(config=None, limit: int = 2000) -> int:
    """Pousse les produits informels récents vers Supabase."""
    headers, base_url = _headers()
    session = get_session(config or load_config())
    prods = session.query(ProduitInformel).order_by(ProduitInformel.id.desc()).limit(limit).all()
    rows = [_serialize(p) for p in prods]
    session.close()
    n = _upsert("produits_informel", rows, headers, base_url)
    logger.info(f"Supabase sync Informel: {n}/{len(rows)}")
    return n


def sync_entreprises(config=None) -> int:
    """Pousse toutes les entreprises vers Supabase."""
    headers, base_url = _headers()
    session = get_session(config or load_config())
    ents = session.query(Entreprise).all()
    rows = [_serialize(e) for e in ents]
    session.close()
    n = _upsert("entreprises", rows, headers, base_url)
    logger.info(f"Supabase sync Entreprises: {n}/{len(rows)}")
    return n


def sync_all(config=None) -> dict:
    """Sync complète vers Supabase."""
    results = {}
    try:
        results["aos"]        = sync_aos(config)
        results["informel"]   = sync_informel(config)
        results["entreprises"] = sync_entreprises(config)
        logger.info(f"Supabase sync complète: {results}")
    except ValueError as e:
        logger.error(f"Supabase non configuré: {e}")
    except Exception as e:
        logger.error(f"Supabase sync erreur: {e}")
    return results


def run(config=None) -> int:
    results = sync_all(config)
    return sum(results.values())
