"""
Point d'entrée Streamlit Cloud.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

# ── Secrets → env vars ────────────────────────────────────────────────────────
_DB_URL = None
try:
    import streamlit as st
    if hasattr(st, "secrets") and st.secrets:
        for k, v in st.secrets.items():
            if isinstance(v, str):
                os.environ.setdefault(k, v)
            elif hasattr(v, 'items'):
                for kk, vv in v.items():
                    os.environ.setdefault(kk, str(vv))
        if "database" in st.secrets and "DATABASE_URL" in st.secrets["database"]:
            _DB_URL = st.secrets["database"]["DATABASE_URL"]
            os.environ["DATABASE_URL"] = _DB_URL
        elif "DATABASE_URL" in st.secrets:
            _DB_URL = st.secrets["DATABASE_URL"]
            os.environ["DATABASE_URL"] = _DB_URL
except Exception:
    pass

if not _DB_URL:
    _DB_URL = os.environ.get("DATABASE_URL", "")
    if _DB_URL:
        os.environ["DATABASE_URL"] = _DB_URL

# ── Monkey-patch get_engine pour bypasser config.yaml ────────────────────────
if _DB_URL and _DB_URL.startswith("postgresql"):
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        import src.database.models as _models
        _pg_engine = create_engine(
            _DB_URL,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10,
                          "options": "-c statement_timeout=20000"},
        )
        _models.get_engine = lambda cfg=None: _pg_engine
        _Session = sessionmaker(bind=_pg_engine)
        _models.get_session = lambda cfg=None: _Session()
    except Exception:
        pass

# ── Lancement du dashboard ────────────────────────────────────────────────────
try:
    from src.dashboard.app import *
except Exception as _boot_err:
    import streamlit as st
    import traceback
    st.set_page_config(page_title="Erreur démarrage", page_icon="❌")
    st.error(f"**Erreur au démarrage :** {_boot_err}")
    st.code(traceback.format_exc(), language="python")
    st.info("Vérifiez que DATABASE_URL est configuré dans Secrets.")
    st.stop()
