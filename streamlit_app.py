"""
Point d'entree Streamlit Cloud.
"""
import sys
import os
import importlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

# -- Secrets -> env vars -------------------------------------------------------
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
            _DB_URL = str(st.secrets["database"]["DATABASE_URL"])
        elif "DATABASE_URL" in st.secrets:
            _DB_URL = str(st.secrets["DATABASE_URL"])
except Exception:
    pass

if not _DB_URL:
    _DB_URL = os.environ.get("DATABASE_URL", "")

# -- Nettoyer l'URL (les retours a la ligne dans la textarea corrompent l'URL) -
if _DB_URL:
    _DB_URL = _DB_URL.replace("\n", "").replace("\r", "").replace(" ", "").strip()
    os.environ["DATABASE_URL"] = _DB_URL

# -- Monkey-patch get_engine pour bypasser config.yaml ------------------------
if _DB_URL and _DB_URL.startswith("postgresql"):
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        import src.database.models as _models
        _pg_engine = create_engine(
            _DB_URL,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10, "sslmode": "require"},
        )
        _models.get_engine = lambda cfg=None: _pg_engine
        _Session = sessionmaker(bind=_pg_engine)
        _models.get_session = lambda cfg=None: _Session()
    except Exception:
        pass

# -- Lancement du dashboard ---------------------------------------------------
try:
    if "src.dashboard.app" in sys.modules:
        importlib.reload(sys.modules["src.dashboard.app"])
    else:
        import src.dashboard.app  # noqa: F401
except Exception as _boot_err:
    import streamlit as st
    import traceback
    try:
        st.set_page_config(page_title="Erreur", page_icon="X")
    except Exception:
        pass
    st.error(f"Erreur au demarrage : {_boot_err}")
    st.code(traceback.format_exc(), language="python")
    st.stop()
