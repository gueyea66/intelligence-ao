"""
Point d'entrée Streamlit Cloud.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# Charger les secrets dans env vars avant tout import
try:
    import streamlit as st
    if hasattr(st, "secrets") and st.secrets:
        for k, v in st.secrets.items():
            if isinstance(v, str):
                os.environ.setdefault(k, v)
            elif hasattr(v, 'items'):
                for kk, vv in v.items():
                    os.environ.setdefault(kk, str(vv))
except Exception:
    pass

from src.dashboard.app import *
