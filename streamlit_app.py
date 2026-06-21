"""
Point d'entrée Streamlit Cloud.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

# Charger les secrets dans env vars
try:
    if hasattr(st, "secrets") and st.secrets:
        for k, v in st.secrets.items():
            if isinstance(v, str):
                os.environ.setdefault(k, v)
            elif hasattr(v, 'items'):
                for kk, vv in v.items():
                    os.environ.setdefault(kk, str(vv))
except Exception:
    pass

st.set_page_config(page_title="Intel Commerciale AO", page_icon="🌍", layout="wide")
st.title("🌍 Intelligence Commerciale — Afrique de l'Ouest")

db_url = os.getenv("DATABASE_URL", "")
if not db_url:
    st.error("❌ DATABASE_URL non configuré dans les secrets Streamlit.")
    st.stop()

st.success(f"✅ DATABASE_URL détecté : `{db_url[:40]}...`")

with st.spinner("Connexion à Supabase..."):
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(db_url, connect_args={"connect_timeout": 8,
                                                      "options": "-c statement_timeout=10000"})
        with engine.connect() as conn:
            nb_p  = conn.execute(text("SELECT COUNT(*) FROM produits")).scalar()
            nb_ao = conn.execute(text("SELECT COUNT(*) FROM appels_offres")).scalar()
            nb_in = conn.execute(text("SELECT COUNT(*) FROM annonces_informel")).scalar()
        st.success("✅ Supabase connecté !")
    except Exception as e:
        st.error(f"❌ Erreur connexion : {e}")
        st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Produits", f"{nb_p:,}")
c2.metric("Appels d'offres", f"{nb_ao:,}")
c3.metric("Annonces informel", f"{nb_in:,}")

st.divider()
st.info("Dashboard complet en cours de chargement... (Cette page de test confirme que Supabase est connecté)")

if st.button("Charger le dashboard complet"):
    from src.dashboard.app import *
