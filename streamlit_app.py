"""
Point d'entrée Streamlit Cloud.
Streamlit Cloud cherche streamlit_app.py à la racine du repo.
"""
import sys
import os

# Ajouter le dossier racine au path
sys.path.insert(0, os.path.dirname(__file__))

# Charger les variables d'environnement depuis st.secrets si dispo
try:
    import streamlit as st
    if hasattr(st, "secrets") and st.secrets:
        for k, v in st.secrets.items():
            if isinstance(v, str):
                os.environ.setdefault(k, v)
            elif hasattr(v, 'items'):
                for kk, vv in v.items():
                    if isinstance(vv, str):
                        os.environ.setdefault(kk, vv)
                    else:
                        os.environ.setdefault(kk, str(vv))
except Exception:
    pass

# Lancer l'app principale
from src.dashboard.app import *
