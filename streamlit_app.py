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
except Exception:
    pass

# ── Fallback env var (si secrets non configurés, utilise env DATABASE_URL) ────
if not _DB_URL:
    _DB_URL = os.environ.get("DATABASE_URL", "")
    if _DB_URL:
        os.environ["DATABASE_URL"] = _DB_URL

# ── Patch config.yaml pour pointer sur PostgreSQL ────────────────────────────
try:
    import yaml
    cfg_path = Path(__file__).parent / "config" / "config.yaml"
    with open(cfg_path) as f:
        _cfg = yaml.safe_load(f)
    _cfg["database"]["type"] = "postgresql"
    _cfg["database"]["postgresql_url"] = _DB_URL
    with open(cfg_path, "w") as f:
        yaml.dump(_cfg, f, allow_unicode=True, default_flow_style=False)
except Exception:
    pass

from src.dashboard.app import *
