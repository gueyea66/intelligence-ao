"""
Dashboard Intelligence Commerciale AO — Sprint 4
Plotly interactif : drill-down, insights statistiques, conjoncture, anomalies.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.utils.config_loader import load_config
from src.database.models import get_session, AppelOffre, Produit, AnnoncInformel, Entreprise
from src.database.db import stats_summary


def _get_distinct(session, column) -> list:
    try:
        rows = session.query(column).distinct().filter(column.isnot(None)).all()
        return sorted([r[0] for r in rows if r[0]])
    except Exception:
        return []


st.set_page_config(
    page_title="Intel Commerciale AO",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
div[data-testid="metric-container"] {
    background: linear-gradient(135deg,#1565c0,#0d47a1);
    border-radius:10px; padding:12px; color:white;
}
div[data-testid="metric-container"] label { color:rgba(255,255,255,0.8)!important; }
div[data-testid="metric-container"] div[data-testid="metric-value"] { color:white!important; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_config():
    import os
    # Sur Streamlit Cloud : injecter les secrets dans l'env
    try:
        for k, v in st.secrets.items():
            if isinstance(v, str):
                os.environ.setdefault(k, v)
            elif isinstance(v, dict):
                for kk, vv in v.items():
                    os.environ.setdefault(kk, str(vv))
    except Exception:
        pass
    return load_config()

@st.cache_resource
def get_db_session():
    import os
    from src.database.models import get_engine, Base
    from sqlalchemy.orm import sessionmaker
    cfg = get_config()
    # Supabase PostgreSQL si DATABASE_URL configuré, sinon SQLite local
    db_url = os.getenv("DATABASE_URL", "")
    if db_url and db_url.startswith("postgresql"):
        from sqlalchemy import create_engine
        engine = create_engine(db_url, pool_pre_ping=True)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        return Session()
    session = get_session(cfg)
    # Test que les tables existent (SQLite peut etre vide sur Streamlit Cloud)
    try:
        from src.database.models import Produit
        session.query(Produit).count()
    except Exception:
        return None
    return session

@st.cache_data(ttl=300)
def load_produits_df():
    try:
        session = get_db_session()
    except Exception:
        return pd.DataFrame()
    if session is None:
        return pd.DataFrame()
    try:
        produits = session.query(Produit).filter(
            Produit.prix_actuel.isnot(None),
            Produit.prix_actuel > 100,
            Produit.prix_actuel < 20_000_000,
        ).all()
    except Exception:
        return pd.DataFrame()
    if not produits:
        return pd.DataFrame()
    return pd.DataFrame([{
        "id":        str(p.id),
        "Marque":    p.marque or "—",
        "Modèle":    (p.modele or "")[:60],
        "Catégorie": p.categorie_1 or "Divers",
        "Sous-cat":  p.categorie_2 or "",
        "Prix":      p.prix_actuel,
        "Barré":     p.prix_barre,
        "Promo":     p.promotion,
        "Source":    p.source,
        "Pays":      p.pays or "Sénégal",
        "Date":      p.date_collecte,
    } for p in produits])

@st.cache_data(ttl=300)
def load_insights():
    try:
        from src.analytics.insights_engine import generer_insights
        return generer_insights(get_config())
    except Exception:
        return {"nb_produits": 0, "distribution_cats": {}, "nb_anomalies": 0,
                "entropie_marche": 0.0, "nb_sources": 0}

@st.cache_data(ttl=600)
def load_macro_df():
    try:
        from src.database.models import DonneeMacro
        session = get_db_session()
        rows = session.query(DonneeMacro).order_by(DonneeMacro.pays, DonneeMacro.annee).all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([{
            "Pays":        r.pays,
            "Indicateur":  r.indicateur,
            "Catégorie":   r.categorie,
            "Année":       r.annee,
            "Valeur":      r.valeur,
            "Unité":       r.unite,
            "Source":      r.source,
        } for r in rows])
    except Exception:
        return pd.DataFrame()


config  = get_config()
try:
    session = get_db_session()
except Exception:
    session = None

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌍 Intel Commerciale")
    st.caption("Afrique de l'Ouest — Sprint 4")
    st.divider()

    try:
        stats = stats_summary(config)
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Produits", f"{stats['nb_produits']:,}")
            st.metric("AOs actifs", stats["nb_aos_actifs"])
        with c2:
            st.metric("🔴 Prioritaires", stats["ao_prioritaires"])
            st.metric("Informel", stats["nb_informel"])
    except Exception:
        st.info("Base de données non connectée — configurez DATABASE_URL dans Secrets.")

    st.divider()
    if st.button("🔄 Rafraîchir tout"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

    st.divider()
    st.caption("Commandes :")
    st.code("python main.py scrape\npython main.py score", language="bash")


# ── Onglets ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Insights",
    "📦 Catalogue",
    "📋 Appels d'Offres",
    "🌍 Conjoncture",
    "🏪 Informel",
    "🤝 Réseau",
])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1 — INSIGHTS STATISTIQUES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    st.header("📊 Insights & Analyse de Marché")

    df = load_produits_df()
    if df.empty:
        st.info("Lancer : `python main.py scrape --source ecommerce`")
    else:
        insights = load_insights()

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Produits analysés", f"{insights['nb_produits']:,}")
        k2.metric("Catégories", len(insights["distribution_cats"]))
        k3.metric("Anomalies prix", insights["nb_anomalies"])
        k4.metric("Diversité marché (H)", f"{insights['entropie_marche']:.2f}")
        k5.metric("Sources actives", insights.get("nb_sources", "—"))

        st.divider()
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Distribution produits par catégorie")
            dist = insights["distribution_cats"]
            fig = px.pie(
                values=list(dist.values()),
                names=list(dist.keys()),
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Bold,
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(showlegend=False, height=380, margin=dict(t=20,b=20))
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Prix moyen & médian par catégorie")
            cats     = list(insights["stats_categories"].keys())
            moyennes = [insights["stats_categories"][c].get("mean", 0) for c in cats]
            medianes = [insights["stats_categories"][c].get("median", 0) for c in cats]

            fig2 = go.Figure()
            fig2.add_trace(go.Bar(name="Moyenne", x=cats, y=moyennes, marker_color="#1565c0"))
            fig2.add_trace(go.Bar(name="Médiane", x=cats, y=medianes, marker_color="#42a5f5"))
            fig2.update_layout(barmode="group", height=380,
                               xaxis_tickangle=-30, yaxis_title="XOF",
                               margin=dict(t=20, b=80))
            st.plotly_chart(fig2, use_container_width=True)

        st.divider()
        col3, col4 = st.columns(2)

        with col3:
            st.subheader("📦 Drill-down catégorie")
            cat_sel = st.selectbox("Catégorie", list(insights["stats_categories"].keys()))
            s = insights["stats_categories"].get(cat_sel, {})
            if s:
                df_cat = df[df["Catégorie"] == cat_sel]["Prix"].dropna()
                if not df_cat.empty:
                    fig_box = go.Figure()
                    fig_box.add_trace(go.Box(y=df_cat, name=cat_sel,
                                             boxpoints="outliers",
                                             marker_color="#1565c0"))
                    fig_box.update_layout(height=280, margin=dict(t=10,b=10))
                    st.plotly_chart(fig_box, use_container_width=True)
                c_a, c_b, c_c = st.columns(3)
                c_a.metric("Nb produits", s.get("n", 0))
                c_b.metric("Prix médian", f"{s.get('median',0):,.0f} XOF")
                c_c.metric("CV (volatilité)", f"{s.get('cv',0):.1f}%")

        with col4:
            st.subheader("🏭 Concentration marché (HHI)")
            hhi_data = insights.get("hhi_par_categorie", {})
            if hhi_data:
                hhi_rows = [{"Catégorie": c, "HHI": v["hhi"],
                             "Interprétation": v["interpretation"],
                             "Nb acteurs": v["nb_acteurs"]}
                            for c, v in hhi_data.items()]
                df_hhi = pd.DataFrame(hhi_rows).sort_values("HHI", ascending=False)
                fig_hhi = px.bar(df_hhi, x="Catégorie", y="HHI",
                                 color="HHI",
                                 color_continuous_scale=["#4caf50","#ff9800","#f44336"],
                                 range_color=[0, 5000],
                                 hover_data=["Interprétation","Nb acteurs"])
                fig_hhi.add_hline(y=1500, line_dash="dash", line_color="orange",
                                  annotation_text="Seuil concurrentiel")
                fig_hhi.add_hline(y=2500, line_dash="dash", line_color="red",
                                  annotation_text="Seuil concentration")
                fig_hhi.update_layout(height=300, margin=dict(t=10,b=60))
                st.plotly_chart(fig_hhi, use_container_width=True)
            else:
                st.info("HHI : données insuffisantes")

        st.divider()
        st.subheader(f"⚠️ Anomalies de prix ({len(insights['anomalies_prix'])})")
        if insights["anomalies_prix"]:
            df_ano = pd.DataFrame(insights["anomalies_prix"])
            fig_ano = px.scatter(
                df_ano, x="produit", y="prix",
                size="z_score", color="deviation",
                color_discrete_map={"sur-évalué":"#f44336","sous-évalué":"#4caf50"},
                hover_data=["z_score","categorie","source"],
            )
            fig_ano.update_layout(height=300, xaxis_tickangle=-30, margin=dict(t=10,b=100))
            st.plotly_chart(fig_ano, use_container_width=True)
            with st.expander("Détail"):
                st.dataframe(df_ano, hide_index=True)

        st.divider()
        st.subheader("🏆 Top 20 marques")
        top_m = insights.get("top_marques", {})
        if top_m:
            df_m = pd.DataFrame({"Marque": list(top_m.keys()), "Produits": list(top_m.values())})
            fig_m = px.bar(df_m.sort_values("Produits", ascending=True).tail(20),
                           x="Produits", y="Marque", orientation="h",
                           color="Produits", color_continuous_scale="Blues")
            fig_m.update_layout(height=450, margin=dict(t=10,l=120))
            st.plotly_chart(fig_m, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2 — CATALOGUE PRODUITS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.header("📦 Catalogue Produits")
    df = load_produits_df()

    if df.empty:
        st.info("Aucun produit. Lancer : `python main.py scrape --source ecommerce`")
    else:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            f_cat = st.selectbox("Catégorie", ["Toutes"] + sorted(df["Catégorie"].unique().tolist()), key="cat2")
        with col2:
            f_src = st.selectbox("Source", ["Toutes"] + sorted(df["Source"].unique().tolist()), key="src2")
        with col3:
            prix_range = st.slider("Prix (XOF)", int(df["Prix"].min()),
                                   int(min(df["Prix"].max(), 5_000_000)), (0, 500_000))
        with col4:
            f_promo = st.checkbox("Promos uniquement")

        dff = df.copy()
        if f_cat != "Toutes": dff = dff[dff["Catégorie"] == f_cat]
        if f_src != "Toutes": dff = dff[dff["Source"]    == f_src]
        if f_promo:           dff = dff[dff["Promo"]      == True]
        dff = dff[(dff["Prix"] >= prix_range[0]) & (dff["Prix"] <= prix_range[1])]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Filtrés", f"{len(dff):,}")
        k2.metric("Prix moyen",  f"{dff['Prix'].mean():,.0f} XOF" if len(dff) else "—")
        k3.metric("Prix médian", f"{dff['Prix'].median():,.0f} XOF" if len(dff) else "—")
        k4.metric("Promos", len(dff[dff["Promo"] == True]))

        st.dataframe(
            dff[["Marque","Modèle","Catégorie","Sous-cat","Prix","Barré","Promo","Source","Date"]].head(500),
            use_container_width=True, hide_index=True, height=300,
        )

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            if len(dff) > 5:
                fig = px.histogram(dff, x="Prix", nbins=50, color_discrete_sequence=["#1565c0"],
                                   title="Distribution des prix")
                fig.update_layout(height=300, margin=dict(t=30,b=10))
                st.plotly_chart(fig, use_container_width=True)
        with col_g2:
            if len(dff) > 5:
                top_sc = dff["Sous-cat"].value_counts().head(8).index
                dff_sc = dff[dff["Sous-cat"].isin(top_sc)]
                if not dff_sc.empty:
                    fig2 = px.box(dff_sc, x="Sous-cat", y="Prix", color="Sous-cat",
                                  points="outliers", title="Box plot par sous-catégorie")
                    fig2.update_layout(height=300, showlegend=False,
                                       xaxis_tickangle=-30, margin=dict(t=30,b=80))
                    st.plotly_chart(fig2, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3 — APPELS D'OFFRES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.header("📋 Appels d'Offres")

    seuil_h = config["scoring"]["seuils"]["priorite_haute"]
    seuil_s = config["scoring"]["seuils"]["a_surveiller"]

    if session is None:
        st.info("Base de données non connectée — configurez DATABASE_URL dans les Secrets Streamlit.")
    else:
        try:
            total_aos  = session.query(AppelOffre).count()
            actifs     = session.query(AppelOffre).filter(AppelOffre.date_limite >= datetime.utcnow()).count()
            hauts      = session.query(AppelOffre).filter(AppelOffre.score >= seuil_h).count()
            surveiller = session.query(AppelOffre).filter(
                AppelOffre.score >= seuil_s, AppelOffre.score < seuil_h).count()
        except Exception:
            st.error("Erreur de connexion base de données.")
            total_aos = actifs = hauts = surveiller = 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total AOs", total_aos)
        k2.metric("Actifs", actifs)
        k3.metric("🔴 HAUTE priorité", hauts)
        k4.metric("🟡 À surveiller", surveiller)

        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            f_pays_ao = st.selectbox("Pays", ["Tous"] + _get_distinct(session, AppelOffre.pays), key="ao_pays")
        with col2:
            f_src_ao = st.selectbox("Source", ["Toutes"] + _get_distinct(session, AppelOffre.source), key="ao_src")
        with col3:
            score_min = st.slider("Score minimum", 0, 100, 0, key="ao_score")

        try:
            q_ao = session.query(AppelOffre)
            if f_pays_ao != "Tous":  q_ao = q_ao.filter(AppelOffre.pays == f_pays_ao)
            if f_src_ao != "Toutes": q_ao = q_ao.filter(AppelOffre.source == f_src_ao)
            if score_min > 0:         q_ao = q_ao.filter(AppelOffre.score >= score_min)
            aos = q_ao.order_by(AppelOffre.score.desc().nullslast()).limit(500).all()
        except Exception:
            aos = []

    if session and aos:
        rows = []
        for ao in aos:
            score  = ao.score or 0
            niveau = "🔴 HAUTE" if score >= seuil_h else ("🟡 SURVEILLER" if score >= seuil_s else "⚪ ARCHIVÉ")
            rows.append({
                "Score":    f"{score:.0f}" if score else "—",
                "Niveau":   niveau,
                "Source":   ao.source,
                "Référence":ao.reference or "",
                "Objet":    (ao.objet or "")[:80],
                "Entité":   ao.entite or "",
                "Pays":     ao.pays or "",
                "Budget":   f"{ao.budget_estime:,.0f} {ao.devise}" if ao.budget_estime else "—",
                "Jours":    ao.jours_restants,
            })
        df_ao = pd.DataFrame(rows)
        st.dataframe(df_ao, use_container_width=True, hide_index=True, height=300)

        col_g1, col_g2, col_g3 = st.columns(3)
        with col_g1:
            scores = [ao.score for ao in aos if ao.score]
            if scores:
                fig_s = px.histogram(scores, nbins=20, color_discrete_sequence=["#1565c0"],
                                     title="Distribution scores")
                fig_s.add_vline(x=seuil_s, line_dash="dash", line_color="orange")
                fig_s.add_vline(x=seuil_h, line_dash="dash", line_color="red")
                fig_s.update_layout(height=250, margin=dict(t=30,b=10))
                st.plotly_chart(fig_s, use_container_width=True)
        with col_g2:
            pays_count = df_ao["Pays"].value_counts()
            fig_p = px.bar(pays_count, title="AOs par pays",
                           color_discrete_sequence=["#1565c0"])
            fig_p.update_layout(height=250, margin=dict(t=30,b=30))
            st.plotly_chart(fig_p, use_container_width=True)
        with col_g3:
            jours = [ao.jours_restants for ao in aos if ao.jours_restants is not None]
            if jours:
                fig_j = px.histogram(jours, nbins=15, title="Délais restants",
                                     color_discrete_sequence=["#42a5f5"])
                fig_j.add_vline(x=7, line_dash="dash", line_color="red", annotation_text="7j")
                fig_j.update_layout(height=250, margin=dict(t=30,b=10))
                st.plotly_chart(fig_j, use_container_width=True)

        st.divider()
        refs = [ao.reference for ao in aos if ao.reference]
        if refs:
            ref_sel = st.selectbox("Détail AO", refs[:50])
            ao_sel  = next((a for a in aos if a.reference == ref_sel), None)
            if ao_sel:
                with st.expander("📄 Fiche complète", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write(f"**Référence :** {ao_sel.reference}")
                        st.write(f"**Source :** {ao_sel.source}")
                        st.write(f"**Entité :** {ao_sel.entite or '—'}")
                    with c2:
                        st.write(f"**Score :** {ao_sel.score}")
                        st.write(f"**Pays :** {ao_sel.pays}")
                        st.write(f"**Budget :** {ao_sel.budget_estime:,.0f}" if ao_sel.budget_estime else "**Budget :** —")
                    with c3:
                        st.write(f"**Jours restants :** {ao_sel.jours_restants}")
                        if ao_sel.url_source:
                            st.markdown(f"[🔗 Voir l'AO]({ao_sel.url_source})")
                    st.write("**Objet :**", ao_sel.objet or "—")

                    if ao_sel.detail_scores:
                        try:
                            detail = json.loads(ao_sel.detail_scores)
                            fig_d = px.bar(x=list(detail.keys()), y=list(detail.values()),
                                           labels={"x":"Critère","y":"Score"},
                                           color=list(detail.values()),
                                           color_continuous_scale="Blues")
                            fig_d.update_layout(height=250, margin=dict(t=10,b=60))
                            st.plotly_chart(fig_d, use_container_width=True)
                        except Exception:
                            pass
    else:
        st.info("Aucun AO. Lancer : `python main.py scrape --source ao && python main.py score`")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 4 — CONJONCTURE ÉCONOMIQUE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab4:
    st.header("🌍 Conjoncture Économique — Afrique de l'Ouest")

    df_macro = load_macro_df()

    if df_macro.empty:
        st.warning("Données macro non encore collectées.")
        if st.button("🚀 Collecter maintenant (World Bank API)"):
            with st.spinner("Collecte en cours..."):
                from src.scrapers.macro import world_bank
                n = world_bank.run(config)
                st.cache_data.clear()
                st.success(f"✅ {n} indicateurs collectés !")
                st.rerun()
    else:
        pays_disponibles = sorted(df_macro["Pays"].unique().tolist())
        cats_disponibles = sorted(df_macro["Catégorie"].unique().tolist())

        col1, col2 = st.columns(2)
        with col1:
            pays_sel = st.multiselect("Pays", pays_disponibles, default=pays_disponibles[:4])
        with col2:
            cat_sel = st.selectbox("Thème", cats_disponibles)

        dff_m = df_macro[(df_macro["Pays"].isin(pays_sel)) & (df_macro["Catégorie"] == cat_sel)]

        if not dff_m.empty:
            indicateurs = dff_m["Indicateur"].unique().tolist()
            ind_sel = st.selectbox("Indicateur", indicateurs)
            dff_ind = dff_m[dff_m["Indicateur"] == ind_sel]

            fig_m = px.line(dff_ind, x="Année", y="Valeur", color="Pays",
                            title=f"{ind_sel}", markers=True,
                            color_discrete_sequence=px.colors.qualitative.Bold)
            fig_m.update_layout(height=400, margin=dict(t=40,b=20))
            st.plotly_chart(fig_m, use_container_width=True)

            derniere = dff_ind.sort_values("Année", ascending=False).groupby("Pays").first().reset_index()
            fig_bar = px.bar(derniere, x="Pays", y="Valeur", color="Pays", text="Valeur",
                             title="Dernière valeur disponible",
                             color_discrete_sequence=px.colors.qualitative.Bold)
            fig_bar.update_traces(texttemplate='%{text:.2f}', textposition='outside')
            fig_bar.update_layout(height=320, showlegend=False, margin=dict(t=30,b=10))
            st.plotly_chart(fig_bar, use_container_width=True)

        # Heatmap comparatif
        st.divider()
        st.subheader("🗺️ Comparatif régional")
        indicateurs_pivot = {
            "PIB":       "Croissance PIB (%)",
            "Inflation": "Inflation CPI (%)",
            "Commerce":  "Exportations % PIB",
        }
        rows_heat = []
        for theme, ind in indicateurs_pivot.items():
            df_ind = df_macro[df_macro["Indicateur"] == ind]
            if df_ind.empty: continue
            for pays, row in df_ind.sort_values("Année", ascending=False).groupby("Pays").first().iterrows():
                rows_heat.append({"Pays": pays, "Indicateur": theme, "Valeur": row["Valeur"]})

        if rows_heat:
            df_heat = pd.DataFrame(rows_heat)
            pivot = df_heat.pivot(index="Pays", columns="Indicateur", values="Valeur")
            fig_heat = px.imshow(pivot, color_continuous_scale="RdYlGn",
                                 title="Heatmap régionale", aspect="auto")
            fig_heat.update_layout(height=400, margin=dict(t=40,b=20))
            st.plotly_chart(fig_heat, use_container_width=True)

        # Publications
        st.divider()
        st.subheader("📚 Publications & Études")
        try:
            from src.database.models import EtudeConjoncture
            etudes = session.query(EtudeConjoncture).order_by(
                EtudeConjoncture.date_collecte.desc()).limit(50).all()
            if etudes:
                df_etudes = pd.DataFrame([{
                    "Source": e.source,
                    "Titre":  (e.titre or "")[:100],
                    "Pays":   e.pays or "",
                    "PDF":    "✅" if e.url_pdf else "—",
                    "Lien":   e.url_source or "",
                } for e in etudes])
                st.dataframe(df_etudes, use_container_width=True, hide_index=True)
            else:
                st.info("Lancer `python main.py scrape --source macro`")
        except Exception:
            st.info("Lancer `python main.py init` pour initialiser les tables macro")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 5 — MARCHÉ INFORMEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab5:
    st.header("🏪 Marché Informel")

    try:
        total_inf = session.query(AnnoncInformel).count() if session else 0
        nb_zones  = len(_get_distinct(session, AnnoncInformel.vendeur_zone)) if session else 0
        avec_prix = session.query(AnnoncInformel).filter(AnnoncInformel.prix_unitaire.isnot(None)).count() if session else 0
    except Exception:
        total_inf = nb_zones = avec_prix = 0

    k1, k2, k3 = st.columns(3)
    k1.metric("Total annonces", total_inf)
    k2.metric("Zones couvertes", nb_zones)
    k3.metric("Avec prix", avec_prix)

    col1, col2, col3 = st.columns(3)
    with col1:
        f_zone = st.selectbox("Zone", ["Toutes"] + (_get_distinct(session, AnnoncInformel.vendeur_zone) if session else []))
    with col2:
        f_type_inf = st.selectbox("Type", ["Tous", "offre", "demande"])
    with col3:
        recherche = st.text_input("🔍 Recherche produit")

    try:
        q_inf = session.query(AnnoncInformel) if session else None
        if q_inf is not None:
            if f_zone != "Toutes":   q_inf = q_inf.filter(AnnoncInformel.vendeur_zone == f_zone)
            if f_type_inf != "Tous": q_inf = q_inf.filter(AnnoncInformel.type == f_type_inf)
            if recherche:            q_inf = q_inf.filter(AnnoncInformel.produit.ilike(f"%{recherche}%"))
            annonces = q_inf.order_by(AnnoncInformel.date_collecte.desc()).limit(500).all()
        else:
            annonces = []
    except Exception:
        annonces = []

    if annonces:
        df_inf = pd.DataFrame([{
            "Source":     a.source,
            "Produit":    (a.produit or "")[:60],
            "Prix (XOF)": a.prix_unitaire,
            "Zone":       a.vendeur_zone or "",
            "Type":       a.type or "",
            "Contact":    "✅" if a.contact_disponible else "❌",
            "Date":       a.date_collecte.strftime("%d/%m/%Y") if a.date_collecte else "",
        } for a in annonces])
        st.dataframe(df_inf, use_container_width=True, hide_index=True, height=250)

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            zone_c = df_inf["Zone"].value_counts()
            fig_z = px.bar(zone_c, orientation="h", title="Activité par zone",
                           color_discrete_sequence=["#1565c0"])
            fig_z.update_layout(height=280, margin=dict(t=30,b=10))
            st.plotly_chart(fig_z, use_container_width=True)
        with col_g2:
            src_c = df_inf["Source"].value_counts()
            fig_src = px.pie(src_c, values=src_c.values, names=src_c.index,
                             hole=0.4, title="Par source")
            fig_src.update_layout(height=280, margin=dict(t=30,b=10))
            st.plotly_chart(fig_src, use_container_width=True)
    else:
        st.info("Lancer : `python main.py scrape --source informel`")

    st.divider()
    st.subheader("📝 Saisie terrain")
    with st.form("form_informel"):
        c1, c2 = st.columns(2)
        with c1:
            prod_t  = st.text_input("Produit *")
            zone_t  = st.selectbox("Zone", [z.get("nom","") for z in config.get("geo",{}).get("zones_informel",[])] + ["Autre"])
            type_t  = st.selectbox("Type", ["offre", "demande"])
        with c2:
            prix_t  = st.number_input("Prix (XOF)", min_value=0, value=0)
            qte_t   = st.number_input("Quantité", min_value=1, value=1)
            notes_t = st.text_area("Notes", height=80)
        if st.form_submit_button("✅ Enregistrer") and prod_t:
            ann = AnnoncInformel(
                source="Terrain", date_collecte=datetime.utcnow(),
                type=type_t, produit=prod_t,
                prix_unitaire=prix_t if prix_t > 0 else None,
                devise="XOF", vendeur_zone=zone_t,
                quantite_disponible=qte_t,
                contact_disponible=True, notes_terrain=notes_t,
            )
            session.add(ann)
            session.commit()
            st.success(f"✅ {prod_t} enregistré !")
            st.rerun()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 6 — RÉSEAU
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab6:
    st.header("🤝 Réseau Fournisseurs & Acteurs")

    try:
        total_ent = session.query(Entreprise).count() if session else 0
    except Exception:
        total_ent = 0
    k1, k2, k3 = st.columns(3)
    k1.metric("Entreprises", total_ent)
    k2.metric("Pays", len(_get_distinct(session, Entreprise.pays)) if session else 0)
    k3.metric("Secteurs", len(_get_distinct(session, Entreprise.secteur)) if session else 0)

    col1, col2, col3 = st.columns(3)
    with col1:
        f_type_ent = st.selectbox("Type", ["Tous"] + (_get_distinct(session, Entreprise.type) if session else []))
    with col2:
        f_sect_ent = st.selectbox("Secteur", ["Tous"] + (_get_distinct(session, Entreprise.secteur) if session else []))
    with col3:
        f_pays_ent = st.selectbox("Pays", ["Tous"] + (_get_distinct(session, Entreprise.pays) if session else []), key="ent_pays")

    try:
        q_ent = session.query(Entreprise) if session else None
        if q_ent is not None:
            if f_type_ent != "Tous": q_ent = q_ent.filter(Entreprise.type == f_type_ent)
            if f_sect_ent != "Tous": q_ent = q_ent.filter(Entreprise.secteur == f_sect_ent)
            if f_pays_ent != "Tous": q_ent = q_ent.filter(Entreprise.pays == f_pays_ent)
            entreprises = q_ent.order_by(Entreprise.nom).limit(500).all()
        else:
            entreprises = []
    except Exception:
        entreprises = []

    if entreprises:
        df_ent = pd.DataFrame([{
            "Nom":     e.nom, "Secteur": e.secteur or "",
            "Type":    e.type or "", "Pays": e.pays or "",
            "Ville":   e.ville or "", "Contact": e.contact or "",
        } for e in entreprises])
        st.dataframe(df_ent, use_container_width=True, hide_index=True, height=300)

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            vc = df_ent["Type"].value_counts()
            fig_t = px.pie(vc, values=vc.values, names=vc.index,
                           hole=0.3, title="Par type")
            fig_t.update_layout(height=280, margin=dict(t=30,b=10))
            st.plotly_chart(fig_t, use_container_width=True)
        with col_g2:
            top_s = df_ent["Secteur"].value_counts().head(10)
            fig_s = px.bar(top_s, orientation="h", title="Top secteurs",
                           color_discrete_sequence=["#1565c0"])
            fig_s.update_layout(height=280, margin=dict(t=30,b=10))
            st.plotly_chart(fig_s, use_container_width=True)
    else:
        st.info("Lancer `python main.py scrape --source annuaires` ou ajouter manuellement.")

    st.divider()
    st.subheader("➕ Ajouter une entreprise")
    with st.form("form_ent"):
        c1, c2 = st.columns(2)
        with c1:
            nom_e     = st.text_input("Nom *")
            secteur_e = st.text_input("Secteur")
            type_e    = st.selectbox("Type", ["fournisseur","distributeur","importateur","exportateur","logisticien","autre"])
            pays_e    = st.selectbox("Pays", config["geo"]["pays_prioritaires"])
        with c2:
            ville_e   = st.text_input("Ville")
            taille_e  = st.selectbox("Taille", ["petite","moyenne","grande","très grande"])
            contact_e = st.text_input("Contact")
            notes_e   = st.text_area("Notes", height=80)
        if st.form_submit_button("Enregistrer") and nom_e:
            ent = Entreprise(nom=nom_e, secteur=secteur_e, type=type_e, pays=pays_e,
                             ville=ville_e, taille_estimee=taille_e, contact=contact_e,
                             notes=notes_e, source="Manuel")
            session.add(ent)
            session.commit()
            st.success(f"✅ {nom_e} ajouté !")
            st.rerun()

    st.divider()
    uploaded = st.file_uploader("📂 Import CSV (nom, secteur, type, pays, ville, contact)", type="csv")
    if uploaded:
        try:
            df_up = pd.read_csv(uploaded)
            nb = 0
            for _, row in df_up.iterrows():
                ent = Entreprise(
                    nom=str(row.get("nom","")), secteur=str(row.get("secteur","")),
                    type=str(row.get("type","autre")), pays=str(row.get("pays","Sénégal")),
                    ville=str(row.get("ville","")), contact=str(row.get("contact","")),
                    source="Import CSV",
                )
                session.add(ent)
                nb += 1
            session.commit()
            st.success(f"✅ {nb} entreprises importées !")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
