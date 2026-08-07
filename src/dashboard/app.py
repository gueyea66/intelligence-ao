"""
Dashboard Intelligence Commerciale AO — Sprint 6
Intelligence dans chaque onglet : insights, niches, signaux, opportunités.
"""
import sys, os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.utils.config_loader import load_config
from src.database.models import get_session, AppelOffre, Produit, AnnoncInformel, Entreprise


# ── page config ──────────────────────────────────────────────────────────────
try:
    st.set_page_config(page_title="Intel AO", page_icon="🌍", layout="wide",
                       initial_sidebar_state="expanded")
except Exception:
    pass

st.markdown("""
<style>
div[data-testid="metric-container"] {
    background: linear-gradient(135deg,#1565c0,#0d47a1);
    border-radius:10px; padding:12px; color:white;
}
div[data-testid="metric-container"] label {color:rgba(255,255,255,.8)!important;}
div[data-testid="metric-container"] div[data-testid="metric-value"] {color:white!important;}
.insight-card {
    background:#1e3a5f; border-radius:8px; padding:12px 16px;
    margin:6px 0; border-left:4px solid #42a5f5;
}
.insight-alerte { border-left-color:#ef5350; background:#3b1010; }
.insight-opport { border-left-color:#66bb6a; background:#0f2e12; }
.insight-niche  { border-left-color:#ffa726; background:#2e1b00; }
.insight-risque { border-left-color:#ef9a9a; background:#2e1515; }
.signal-fort    { border-left-color:#f44336; }
.signal-moyen   { border-left-color:#ff9800; }
</style>
""", unsafe_allow_html=True)


# ── helpers ──────────────────────────────────────────────────────────────────
def _card(text: str, kind: str = ""):
    css = {"alerte": "insight-alerte", "opport": "insight-opport",
           "niche": "insight-niche", "risque": "insight-risque"}.get(kind, "insight-card")
    st.markdown(f'<div class="insight-card {css}">{text}</div>', unsafe_allow_html=True)


def _get_distinct(session, col):
    try:
        rows = session.query(col).distinct().filter(col.isnot(None)).all()
        return sorted([r[0] for r in rows if r[0]])
    except Exception:
        return []


# ── cache ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_config():
    try:
        for k, v in st.secrets.items():
            if isinstance(v, str): os.environ.setdefault(k, v)
            elif hasattr(v, 'items'):
                for kk, vv in v.items(): os.environ.setdefault(kk, str(vv))
    except Exception:
        pass
    return load_config()


@st.cache_resource
def get_db():
    import os
    from src.database.models import get_engine, Base
    from sqlalchemy.orm import sessionmaker
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("postgresql"):
        from sqlalchemy import create_engine
        engine = create_engine(db_url, pool_pre_ping=False,
                               connect_args={"connect_timeout":10,"sslmode":"require"})
        with engine.connect() as c:
            try: Base.metadata.create_all(bind=c); c.commit()
            except Exception: c.rollback()
        engine.dispose()
        return sessionmaker(bind=engine)()
    session = get_session(get_config())
    try: session.query(Produit).count()
    except Exception: return None
    return session


@st.cache_data(ttl=300)
def load_ao_df():
    try:
        s = get_db()
        if s is None: return pd.DataFrame()
        aos = s.query(AppelOffre).order_by(AppelOffre.score.desc().nullslast()).all()
        if not aos: return pd.DataFrame()
        rows = []
        for ao in aos:
            sc = float(ao.score or 0)
            rows.append({
                "id": ao.id,
                "Source": ao.source or "",
                "Statut": ao.statut or "",
                "Score": sc,
                "Niveau": "🔴 URGENT" if sc >= 80 else ("🟡 PRIO" if sc >= 60 else "⚪ WATCH"),
                "Objet": (ao.objet or "")[:120],
                "Entite": (ao.entite or "")[:80],
                "Pays": ao.pays or "",
                "Categorie": ao.categorie or "divers",
                "Budget": ao.budget_estime,
                "Devise": ao.devise or "XOF",
                "Jours": ao.jours_restants,
                "Date_pub": ao.date_publication,
                "Date_limite": ao.date_limite,
                "URL": ao.url_source or "",
                "Reference": ao.reference or "",
                "Date_collecte": ao.date_collecte,
            })
        return pd.DataFrame(rows)
    except Exception as e:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def load_macro_df():
    try:
        from src.database.models import DonneeMacro
        s = get_db()
        if s is None: return pd.DataFrame()
        rows = s.query(DonneeMacro).all()
        if not rows: return pd.DataFrame()
        return pd.DataFrame([{
            "Pays": r.pays, "Indicateur": r.indicateur, "Categorie": r.categorie,
            "Annee": r.annee, "Valeur": r.valeur, "Unite": r.unite, "Source": r.source,
        } for r in rows])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_quality_stats():
    """Indicateurs qualite de la base (informel + discussions)."""
    try:
        from sqlalchemy import text as _text
        s = get_db()
        if s is None: return {}
        inf = s.execute(_text("""
            SELECT count(*),
                   count(*) FILTER (WHERE categorie_std IS NOT NULL AND categorie_std != ''),
                   count(*) FILTER (WHERE prix_unitaire > 0),
                   count(*) FILTER (WHERE NOT is_duplicate)
            FROM annonces_informel""")).fetchone()
        disc = s.execute(_text("""
            SELECT count(*), count(*) FILTER (WHERE est_spam), count(*) FILTER (WHERE traite)
            FROM discussions_sociales""")).fetchone()
        return {
            "inf_total": inf[0], "inf_cat": inf[1], "inf_prix": inf[2], "inf_uniques": inf[3],
            "disc_total": disc[0], "disc_spam": disc[1], "disc_traites": disc[2],
        }
    except Exception:
        return {}


@st.cache_data(ttl=300)
def load_annonces():
    try:
        s = get_db()
        if s is None: return []
        return s.query(AnnoncInformel).order_by(AnnoncInformel.date_collecte.desc()).limit(500).all()
    except Exception:
        return []


# ── init ─────────────────────────────────────────────────────────────────────
config  = get_config()
session = get_db()
df_ao   = load_ao_df()
df_mac  = load_macro_df()
annonces = load_annonces()

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌍 Intel AO")
    st.caption("Afrique de l'Ouest")
    st.divider()
    nb_ao = len(df_ao)
    actifs_n = (df_ao["Statut"] == "actif").sum() if not df_ao.empty else 0
    urg_n = (df_ao["Score"] >= 80).sum() if not df_ao.empty else 0
    prio_n = ((df_ao["Score"] >= 60) & (df_ao["Score"] < 80)).sum() if not df_ao.empty else 0
    c1, c2 = st.columns(2)
    c1.metric("Total AOs", f"{nb_ao:,}")
    c2.metric("Actifs", actifs_n)
    c1.metric("🔴 Urgents", urg_n)
    c2.metric("🟡 Prio", prio_n)
    if not df_ao.empty and "Date_collecte" in df_ao.columns:
        dc = pd.to_datetime(df_ao["Date_collecte"]).dt.date.dropna()
        if len(dc):
            st.metric("📅 Jours de scraping", f"{dc.nunique()} j",
                      help=f"Du {dc.min():%d/%m/%Y} au {dc.max():%d/%m/%Y}")
    st.divider()
    if st.button("🔄 Rafraichir"):
        st.cache_data.clear(); st.cache_resource.clear(); st.rerun()


# ── onglets ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Vue d'ensemble",
    "📋 Appels d'Offres",
    "🌍 Conjoncture",
    "🏪 Marché Informel",
    "📡 Signaux",
    "🤝 Réseau",
])


# =============================================================================
# TAB 1 — VUE D'ENSEMBLE INTELLIGENTE
# =============================================================================
with tab1:
    st.header("📊 Vue d'ensemble — Intelligence transversale")

    if df_ao.empty:
        st.warning("Aucun AO en base. Lancer : `python run_all_sources.py`")
    else:
        from src.analytics.intelligence_engine import insights_vue_ensemble

        ins = insights_vue_ensemble(df_ao, df_mac)
        actifs = df_ao[df_ao["Statut"] == "actif"]

        # KPIs
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Total AOs", f"{len(df_ao):,}")
        k2.metric("Actifs", f"{len(actifs):,}")
        k3.metric("🔴 Urgents ≥80", (df_ao["Score"] >= 80).sum())
        k4.metric("🟡 Prioritaires", ((df_ao["Score"] >= 60) & (df_ao["Score"] < 80)).sum())
        k5.metric("Sources", df_ao["Source"].nunique())
        k6.metric("Pays couverts", df_ao["Pays"].nunique())

        # ── Qualité des données ───────────────────────────────────────────
        with st.expander("🧹 Qualité des données — épuration & couverture"):
            q = load_quality_stats()
            statuts = df_ao["Statut"].value_counts()
            nb_doublons = int(statuts.get("doublon", 0))
            nb_hors_scope = int(statuts.get("hors_scope", 0))
            actifs_q = df_ao[df_ao["Statut"] == "actif"]
            nb_a = max(len(actifs_q), 1)
            cat_ok = (~actifs_q["Categorie"].isin(["Autre", "divers", ""])).sum()
            budget_ok = (actifs_q["Budget"].fillna(0) > 0).sum()

            qc1, qc2, qc3, qc4 = st.columns(4)
            qc1.metric("Doublons écartés", nb_doublons,
                       help="Même source + même objet, seul le plus ancien reste actif")
            qc2.metric("Hors scope écartés", nb_hors_scope,
                       help="Publications statistiques (ANSD), liens de navigation, scories de scraping")
            qc3.metric("Actifs catégorisés", f"{100*cat_ok//nb_a}%",
                       help=f"{cat_ok}/{nb_a} AOs actifs avec une vraie catégorie")
            qc4.metric("Actifs avec budget", f"{100*budget_ok//nb_a}%",
                       help="Les sources publient rarement le montant dans le flux — voir la page de l'AO")

            if q:
                qc5, qc6, qc7, qc8 = st.columns(4)
                qc5.metric("Informel : annonces uniques", f"{q['inf_uniques']:,}",
                           help=f"{q['inf_total']:,} lignes brutes collectées (doublons Expat-Dakar marqués)")
                qc6.metric("Informel : catégorisées", f"{100*q['inf_cat']//max(q['inf_total'],1)}%")
                qc7.metric("Informel : avec prix", f"{q['inf_prix']:,}")
                qc8.metric("Discussions : spam filtré", f"{q['disc_spam']}/{q['disc_total']}",
                           help=f"{q['disc_traites']} discussions traitées (sentiment + topics)")

        st.divider()

        # ── Alertes immédiates ────────────────────────────────────────────
        if ins["alertes"]:
            st.subheader("⏰ Action immédiate requise")
            for a in ins["alertes"]:
                url_part = f' — [→ Voir]({a["url"]})' if a.get("url") else ""
                _card(f'**{a["icon"]} {a["titre"]}**<br>{a["detail"]}{url_part}', "alerte")

        col1, col2 = st.columns(2)

        # ── Opportunités ──────────────────────────────────────────────────
        with col1:
            st.subheader("💰 Opportunités détectées")
            if ins["opportunites"]:
                for o in ins["opportunites"]:
                    _card(f'**{o["icon"]} {o["titre"]}**<br><small>{o["detail"]}</small>', "opport")
            else:
                st.info("Lancer le scraper pour enrichir les données.")

        # ── Niches ────────────────────────────────────────────────────────
        with col2:
            st.subheader("💡 Niches identifiées")
            if ins["niches"]:
                for n in ins["niches"]:
                    _card(f'**{n["icon"]} {n["titre"]}**<br><small>{n["detail"]}</small>', "niche")
            if ins["risques"]:
                st.subheader("⚠️ Points de vigilance")
                for r in ins["risques"]:
                    _card(f'**{r["icon"]} {r["titre"]}**<br><small>{r["detail"]}</small>', "risque")

        st.divider()

        # ── Visualisations ────────────────────────────────────────────────
        col3, col4 = st.columns(2)
        with col3:
            src_c = df_ao.groupby("Source").size().reset_index(name="N")
            fig = px.bar(src_c.sort_values("N"), x="N", y="Source", orientation="h",
                         color="Source", color_discrete_sequence=px.colors.qualitative.Bold,
                         title="AOs par source")
            fig.update_layout(height=260, showlegend=False, margin=dict(t=30, b=0, l=0))
            st.plotly_chart(fig, use_container_width=True)

        with col4:
            pays_c = actifs.groupby("Pays").size().reset_index(name="N").sort_values("N", ascending=False).head(10)
            fig2 = px.bar(pays_c.sort_values("N"), x="N", y="Pays", orientation="h",
                          color_discrete_sequence=["#1565c0"], title="Actifs par pays")
            fig2.update_layout(height=260, showlegend=False, margin=dict(t=30, b=0, l=0))
            st.plotly_chart(fig2, use_container_width=True)

        # ── Top urgents ───────────────────────────────────────────────────
        urgents = df_ao[df_ao["Score"] >= 80].sort_values("Score", ascending=False)
        if not urgents.empty:
            st.subheader("🔴 AOs urgents — agir maintenant")
            for _, r in urgents.head(5).iterrows():
                j = f" — **{int(r['Jours'])}j restants**" if pd.notna(r["Jours"]) else ""
                url_lnk = f" [→]({r['URL']})" if r["URL"] else ""
                st.markdown(f"- `{r['Score']:.0f}` **[{r['Source']}]** {r['Objet'][:90]}{j}{url_lnk}")

        # ── Ce que les données disent ensemble ───────────────────────────
        st.divider()
        st.subheader("🧠 Ce que toutes les données disent ensemble")
        nb_actifs = len(actifs)
        top_src = df_ao["Source"].value_counts().index[0] if nb_actifs > 0 else "?"
        top_cat = actifs["Categorie"].value_counts().index[0] if nb_actifs > 0 else "?"
        top_pays = actifs["Pays"].value_counts().index[0] if nb_actifs > 0 else "?"
        score_moy = df_ao["Score"].mean()
        pct_sans_date = round(100 * actifs["Jours"].isna().sum() / max(nb_actifs, 1), 0)

        synthese = f"""
**{len(df_ao)} AOs collectés** depuis {df_ao["Source"].nunique()} sources officielles.

Le marché actuel te dit :
- **{top_pays}** est le pays le plus actif ({actifs["Pays"].value_counts().iloc[0]} AOs actifs) — c'est ton terrain principal.
- **Catégorie dominante : {top_cat}** — si tu n'as pas encore de référence dans ce secteur, c'est urgent.
- **Score moyen {score_moy:.0f}/100** — le niveau de pertinence moyen est {'bon' if score_moy > 55 else 'correct'} mais {(df_ao["Score"] >= 80).sum()} AOs méritent une action immédiate.
- **{pct_sans_date}% des actifs sans date limite** — tu vois moins de la moitié des échéances réelles. Consulter directement les sources pour les AOs sans URL.
- **Source dominante : {top_src}** — {'AfDB = cycle de décaissement actif, fenêtre 6-18 mois' if top_src == 'AfDB' else 'Diversifier les sources pour capturer plus d\'AOs exclusifs'}.

**Signal croisé AOs + macro** : {'Les données macro ne sont pas encore chargées. Lancer la collecte depuis l\'onglet Conjoncture.' if df_mac.empty else 'Les indicateurs macroéconomiques disponibles renforcent la priorisation Sénégal/UEMOA.'}
        """
        st.markdown(synthese)


# =============================================================================
# TAB 2 — APPELS D'OFFRES (filtres + intelligence)
# =============================================================================
with tab2:
    st.header("📋 Appels d'Offres")

    if df_ao.empty:
        st.warning("Aucun AO en base.")
    else:
        all_sources = sorted(df_ao["Source"].unique().tolist())
        default_sources = [s for s in all_sources if s != "MarchesDuSenegal"]

        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        with col1:
            f_src = st.multiselect("Sources", all_sources, default=default_sources)
        with col2:
            f_pays = st.selectbox("Pays", ["Tous"] + sorted(df_ao["Pays"].dropna().unique().tolist()))
        with col3:
            f_cat = st.selectbox("Catégorie", ["Toutes"] + sorted(df_ao["Categorie"].dropna().unique().tolist()))
        with col4:
            score_min = st.number_input("Score min", 0, 100, 0, 10)

        dff = df_ao.copy()
        if f_src:   dff = dff[dff["Source"].isin(f_src)]
        if f_pays != "Tous":   dff = dff[dff["Pays"] == f_pays]
        if f_cat != "Toutes":  dff = dff[dff["Categorie"] == f_cat]
        if score_min > 0:      dff = dff[dff["Score"] >= score_min]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Résultats", len(dff))
        k2.metric("Score moyen", f"{dff['Score'].mean():.0f}" if len(dff) else "—")
        k3.metric("Urgents ≥80", (dff["Score"] >= 80).sum())
        k4.metric("Avec deadline", dff["Jours"].notna().sum())

        # ── Insight contextuel ────────────────────────────────────────────
        if not dff.empty:
            top_c = dff["Categorie"].value_counts().index[0]
            moy = dff["Score"].mean()
            _card(
                f'**🧠 Sur ce filtre :** {len(dff)} AOs — catégorie dominante **{top_c}** — '
                f'score moyen **{moy:.0f}** — '
                f'{"⚠️ filtre trop large, affiner" if len(dff) > 100 else "✅ périmètre exploitable"}',
                "niche"
            )

        st.divider()
        st.dataframe(
            dff[["Score", "Niveau", "Source", "Pays", "Objet", "Entite", "Categorie", "Jours"]]
              .sort_values("Score", ascending=False),
            use_container_width=True, hide_index=True, height=320,
        )

        # Graphiques
        col_g1, col_g2, col_g3 = st.columns(3)
        with col_g1:
            if len(dff) > 2:
                fig = px.histogram(dff[dff["Score"] > 0], x="Score", nbins=20,
                                   color_discrete_sequence=["#1565c0"], title="Distribution scores")
                fig.add_vline(x=60, line_dash="dash", line_color="orange")
                fig.add_vline(x=80, line_dash="dash", line_color="red")
                fig.update_layout(height=220, margin=dict(t=30, b=5))
                st.plotly_chart(fig, use_container_width=True)
        with col_g2:
            pays_c = dff["Pays"].value_counts().head(8)
            if len(pays_c) > 0:
                fig2 = px.bar(pays_c, title="Par pays", color_discrete_sequence=["#1565c0"])
                fig2.update_layout(height=220, margin=dict(t=30, b=30))
                st.plotly_chart(fig2, use_container_width=True)
        with col_g3:
            cat_c = dff["Categorie"].value_counts().head(8)
            if len(cat_c) > 0:
                fig3 = px.pie(cat_c, values=cat_c.values, names=cat_c.index,
                              hole=0.4, title="Par catégorie")
                fig3.update_layout(height=220, margin=dict(t=30, b=5), showlegend=False)
                st.plotly_chart(fig3, use_container_width=True)

        # Fiche détail
        st.divider()
        refs = dff["Reference"].dropna().tolist()[:50]
        if refs:
            ref_sel = st.selectbox("Détail AO", refs)
            row = dff[dff["Reference"] == ref_sel].iloc[0] if ref_sel else None
            if row is not None:
                with st.expander("📄 Fiche complète", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write(f"**Source :** {row['Source']}")
                        st.write(f"**Entité :** {row['Entite'] or '—'}")
                        st.write(f"**Pays :** {row['Pays']}")
                    with c2:
                        st.write(f"**Score :** {row['Score']:.0f} {row['Niveau']}")
                        st.write(f"**Catégorie :** {row['Categorie']}")
                        bgt = f"{row['Budget']:,.0f} {row['Devise']}" if row['Budget'] else "—"
                        st.write(f"**Budget :** {bgt}")
                    with c3:
                        j = f"{int(row['Jours'])} jours" if pd.notna(row["Jours"]) else "—"
                        st.write(f"**Délai restant :** {j}")
                        if row["URL"]:
                            st.markdown(f"[🔗 Voir l'AO officiel]({row['URL']})")
                    st.write("**Objet :**", row["Objet"])
                    # Conseil contextuel
                    if row["Score"] >= 80:
                        _card("🔴 **AO URGENT** — Préparer une offre ou manifester d'intérêt dans les prochains jours.", "alerte")
                    elif row["Score"] >= 60:
                        _card("🟡 **AO PRIORITAIRE** — Évaluer la faisabilité et identifier des partenaires si nécessaire.", "niche")


# =============================================================================
# TAB 3 — CONJONCTURE INTELLIGENTE
# =============================================================================
with tab3:
    st.header("🌍 Conjoncture — Signaux macro pour l'action")

    if df_mac.empty:
        st.warning("Données macro non collectées.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Collecter World Bank API"):
                with st.spinner("Collecte..."):
                    try:
                        from src.scrapers.macro import world_bank
                        n = world_bank.run(config)
                        st.cache_data.clear()
                        st.success(f"✅ {n} indicateurs")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur: {e}")
        with col2:
            st.info("Données World Bank sur PIB, inflation, dette, commerce pour 16 pays d'Afrique de l'Ouest.")
    else:
        from src.analytics.intelligence_engine import insights_conjoncture

        macro_insights = insights_conjoncture(df_mac)

        # ── Intelligence macro ────────────────────────────────────────────
        st.subheader("🧠 Ce que la conjoncture te dit")
        for ins in macro_insights:
            kind = {"pib": "opport", "senegal": "opport", "inflation": "risque",
                    "dette": "opport", "commerce": "niche", "conseil": "niche"}.get(ins["type"], "")
            _card(f'**{ins["icon"]} {ins["titre"]}**<br><small>{ins["detail"]}</small>', kind)

        st.divider()

        # ── Visualisations ────────────────────────────────────────────────
        pays_dispo = sorted(df_mac["Pays"].unique().tolist())
        cats_dispo = sorted(df_mac["Categorie"].unique().tolist())

        col1, col2 = st.columns(2)
        with col1:
            pays_sel = st.multiselect("Pays", pays_dispo, default=pays_dispo[:5])
        with col2:
            cat_sel = st.selectbox("Thème", cats_dispo)

        dff_m = df_mac[(df_mac["Pays"].isin(pays_sel)) & (df_mac["Categorie"] == cat_sel)]
        if not dff_m.empty:
            inds = dff_m["Indicateur"].unique().tolist()
            ind_sel = st.selectbox("Indicateur", inds)
            dff_ind = dff_m[dff_m["Indicateur"] == ind_sel]
            fig = px.line(dff_ind, x="Annee", y="Valeur", color="Pays", title=ind_sel,
                          markers=True, color_discrete_sequence=px.colors.qualitative.Bold)
            fig.update_layout(height=380, margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)

            # Conseil lié à l'indicateur
            if "inflation" in ind_sel.lower():
                _card("💡 **Action :** Inclure une clause de révision des prix dans tes offres si le marché dure > 6 mois dans les pays à forte inflation.", "niche")
            elif "pib" in ind_sel.lower() or "gdp" in ind_sel.lower():
                _card("💡 **Action :** Les pays à PIB +6% ont des budgets publics en expansion — volume d'AOs à la hausse dans 12-18 mois.", "opport")

        # ── Heatmap régionale ─────────────────────────────────────────────
        st.divider()
        st.subheader("🗺️ Carte de chaleur régionale")
        pivot_data = []
        for ind_label, kw in [("PIB", "GDP|Croissance"), ("Inflation", "Inflation|CPI"), ("Commerce", "export|trade")]:
            subset = df_mac[df_mac["Indicateur"].str.contains(kw, case=False, na=False)]
            if not subset.empty:
                last_y = subset["Annee"].max()
                for pays, grp in subset[subset["Annee"] == last_y].groupby("Pays"):
                    pivot_data.append({"Pays": pays, "Indicateur": ind_label, "Valeur": grp["Valeur"].mean()})
        if pivot_data:
            df_heat = pd.DataFrame(pivot_data)
            try:
                piv = df_heat.pivot(index="Pays", columns="Indicateur", values="Valeur")
                fig_h = px.imshow(piv, color_continuous_scale="RdYlGn", title="Comparatif régional", aspect="auto")
                fig_h.update_layout(height=380, margin=dict(t=40, b=20))
                st.plotly_chart(fig_h, use_container_width=True)
            except Exception:
                st.dataframe(df_heat, use_container_width=True, hide_index=True)


# =============================================================================
# TAB 4 — MARCHÉ INFORMEL INTELLIGENT
# =============================================================================
with tab4:
    st.header("🏪 Marché Informel — Veille terrain & niches")

    from src.analytics.intelligence_engine import insights_informel

    inf_data = insights_informel(annonces)

    # ── Pourquoi cet onglet existe ────────────────────────────────────────
    _card(
        "**Pourquoi le marché informel ?** Les prix réels du marché informel sont 20-40% inférieurs "
        "aux devis formels. Capturer ces données te donne un avantage concurrentiel sur les AOs "
        "de fournitures : tu sais exactement quel prix proposer pour être compétitif sans perdre d'argent.",
        "niche"
    )

    # KPIs
    k1, k2, k3 = st.columns(3)
    k1.metric("Observations terrain", len(annonces))
    k2.metric("Avec prix", sum(1 for a in annonces if a.prix_unitaire))
    k3.metric("Zones couvertes", len(set(a.vendeur_zone for a in annonces if a.vendeur_zone)))

    st.divider()

    # ── Insights terrain ─────────────────────────────────────────────────
    if inf_data["insights"]:
        st.subheader("🧠 Ce que tes données terrain disent")
        for ins in inf_data["insights"]:
            _card(f'**{ins["icon"]} {ins["titre"]}**<br><small>{ins["detail"]}</small>')

    # ── Niches recommandées ───────────────────────────────────────────────
    st.divider()
    st.subheader("💡 Niches à surveiller en priorité")
    st.caption("Ces 5 niches croisent le mieux tes AOs actifs avec le marché informel.")

    cols = st.columns(len(inf_data["niches_recommandees"]))
    for col, niche in zip(cols, inf_data["niches_recommandees"]):
        with col:
            st.markdown(f"### {niche['icone']} {niche['niche']}")
            st.markdown(f"**Pourquoi :** {niche['pourquoi']}")
            st.markdown(f"**Surveiller :** _{niche['signaux']}_")

    # ── Guide de saisie terrain ───────────────────────────────────────────
    st.divider()
    col_g, col_f = st.columns([1, 1])

    with col_g:
        st.subheader("📋 Champs utiles à capturer")
        st.caption("Ce que l'IA peut faire avec chaque donnée terrain :")
        for c in inf_data["champs_a_capturer"]:
            req = "🔴 requis" if c["requis"] else "🔵 optionnel"
            st.markdown(f"**{c['champ']}** ({req})")
            st.caption(c["conseil"])

    with col_f:
        st.subheader("➕ Saisie rapide")
        with st.form("form_inf"):
            prod_t  = st.text_input("Produit * (ex: Ciment CEM II 42.5, sac 50kg)")
            c1, c2 = st.columns(2)
            with c1:
                prix_t  = st.number_input("Prix (FCFA)", min_value=0, value=0)
                zone_t  = st.text_input("Zone / quartier")
            with c2:
                type_t  = st.selectbox("Type", ["offre", "demande"])
                qual_t  = st.slider("Qualité (1-5)", 1, 5, 3)
            notes_t = st.text_input("Notes (délai, fournisseur, concurrent...)")
            if st.form_submit_button("✅ Enregistrer") and prod_t and session:
                ann = AnnoncInformel(
                    source="Terrain", date_collecte=datetime.utcnow(),
                    type=type_t, produit=prod_t,
                    prix_unitaire=prix_t if prix_t > 0 else None,
                    devise="XOF", vendeur_zone=zone_t,
                    contact_disponible=True, notes_terrain=notes_t,
                )
                session.add(ann); session.commit()
                st.success(f"✅ Enregistré : {prod_t}")
                st.cache_data.clear(); st.rerun()

    # ── Données existantes ────────────────────────────────────────────────
    if annonces:
        st.divider()
        st.subheader("📊 Observations enregistrées")
        df_inf = pd.DataFrame([{
            "Produit": (a.produit or "")[:50], "Prix (XOF)": a.prix_unitaire,
            "Zone": a.vendeur_zone or "", "Type": a.type or "",
            "Date": a.date_collecte.strftime("%d/%m/%Y") if a.date_collecte else "",
        } for a in annonces])
        st.dataframe(df_inf, use_container_width=True, hide_index=True, height=220)


# =============================================================================
# TAB 5 — SIGNAUX (INTELLIGENCE TEMPS RÉEL)
# =============================================================================
with tab5:
    st.header("📡 Signaux — Détection de patterns & opportunités cachées")

    from src.analytics.intelligence_engine import generer_signaux

    signaux = generer_signaux(df_ao, df_mac, annonces)

    _card(
        "**Qu'est-ce que les signaux ?** Ce sont des patterns que les données révèlent "
        "mais que tu ne verrais pas en parcourant la liste. L'IA cherche des anomalies, "
        "des concentrations inhabituelles, des corrélations entre sources.",
        "niche"
    )

    st.divider()

    if not signaux:
        st.info("Pas assez de données pour générer des signaux. Charger les AOs et les données macro.")
    else:
        # Trier par force
        ordre = {"fort": 0, "moyen": 1, "info": 2, "faible": 3}
        signaux_sorted = sorted(signaux, key=lambda x: ordre.get(x.get("force", "info"), 2))

        for s in signaux_sorted:
            force = s.get("force", "info")
            kind = "alerte" if force == "fort" else ("niche" if force == "moyen" else "")
            css_extra = "signal-fort" if force == "fort" else ("signal-moyen" if force == "moyen" else "")
            _card(
                f'**{s["icon"]} {s["titre"]}**<br>'
                f'<small>{s["detail"]}</small><br>'
                f'<small>→ **Action :** {s["action"]}</small>',
                kind
            )

    # ── Matrice de priorisation ───────────────────────────────────────────
    if not df_ao.empty:
        st.divider()
        st.subheader("🎯 Matrice effort/valeur — Où concentrer ton énergie")

        actifs = df_ao[df_ao["Statut"] == "actif"]
        if not actifs.empty:
            # Score = valeur, jours_restants = urgence (moins = plus urgent)
            df_matrix = actifs[actifs["Jours"].notna() & (actifs["Jours"] >= 0)].copy()
            if len(df_matrix) > 0:
                fig_m = px.scatter(
                    df_matrix.head(50),
                    x="Jours",
                    y="Score",
                    color="Categorie",
                    size="Score",
                    hover_data=["Objet", "Source", "Pays"],
                    title="Score vs Jours restants (bas-gauche = action immédiate)",
                    labels={"Jours": "Jours restants", "Score": "Score de pertinence"},
                    color_discrete_sequence=px.colors.qualitative.Bold,
                )
                fig_m.add_hline(y=60, line_dash="dash", line_color="orange",
                                annotation_text="Seuil prio")
                fig_m.add_vline(x=14, line_dash="dash", line_color="red",
                                annotation_text="< 14j")
                fig_m.update_layout(height=400, margin=dict(t=40, b=20))
                st.plotly_chart(fig_m, use_container_width=True)
                st.caption("Bas gauche (score élevé + peu de jours) = AOs à traiter en priorité absolue.")

    # ── Analyse avancée par catégorie ─────────────────────────────────────
    if not df_ao.empty:
        st.divider()
        st.subheader("📊 Analyse avancée — Pression concurrentielle par secteur")

        actifs = df_ao[df_ao["Statut"] == "actif"]
        cat_stats = actifs.groupby("Categorie").agg(
            nb=("Score", "count"),
            score_moy=("Score", "mean"),
            score_max=("Score", "max"),
            avec_date=("Jours", lambda x: x.notna().sum()),
        ).reset_index()
        cat_stats["visibilite"] = (cat_stats["avec_date"] / cat_stats["nb"] * 100).round(0)
        cat_stats["opportunite"] = (cat_stats["score_moy"] * 0.6 + cat_stats["visibilite"] * 0.4).round(0)
        cat_stats = cat_stats.sort_values("opportunite", ascending=False)

        fig_cat = px.bar(cat_stats.head(10), x="Categorie", y=["nb", "score_moy"],
                         barmode="group", title="Volume vs Score moyen par catégorie",
                         color_discrete_sequence=["#1565c0", "#42a5f5"])
        fig_cat.update_layout(height=300, margin=dict(t=40, b=60))
        st.plotly_chart(fig_cat, use_container_width=True)

        st.caption("Catégories avec score élevé ET volume fort = compétition probable. Catégories avec score élevé ET volume faible = niche peu exploitée.")

        cols = st.columns(3)
        for i, (_, row) in enumerate(cat_stats.head(3).iterrows()):
            with cols[i]:
                st.metric(f"#{i+1} {row['Categorie']}", f"Score opport. {row['opportunite']:.0f}",
                          f"{int(row['nb'])} AOs — vis. {row['visibilite']:.0f}%")


# =============================================================================
# TAB 6 — RÉSEAU
# =============================================================================
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

    if total_ent == 0:
        _card(
            "**💡 Pourquoi construire ce réseau ?** Pour les AOs en consortium obligatoire, "
            "tu as besoin de partenaires identifiés à l'avance. Renseigner les fournisseurs "
            "locaux te permet aussi de valoriser le contenu local dans tes offres — critère "
            "souvent noté dans les AOs AfDB/BM.",
            "niche"
        )

    col1, col2, col3 = st.columns(3)
    with col1:
        f_type = st.selectbox("Type", ["Tous"] + (_get_distinct(session, Entreprise.type) if session else []))
    with col2:
        f_sect = st.selectbox("Secteur", ["Tous"] + (_get_distinct(session, Entreprise.secteur) if session else []))
    with col3:
        f_pays = st.selectbox("Pays", ["Tous"] + (_get_distinct(session, Entreprise.pays) if session else []), key="ent_pays")

    try:
        q = session.query(Entreprise) if session else None
        if q:
            if f_type != "Tous": q = q.filter(Entreprise.type == f_type)
            if f_sect != "Tous": q = q.filter(Entreprise.secteur == f_sect)
            if f_pays != "Tous": q = q.filter(Entreprise.pays == f_pays)
            ents = q.order_by(Entreprise.nom).limit(500).all()
        else:
            ents = []
    except Exception:
        ents = []

    if ents:
        df_ent = pd.DataFrame([{
            "Nom": e.nom, "Secteur": e.secteur or "", "Type": e.type or "",
            "Pays": e.pays or "", "Ville": e.ville or "", "Contact": e.contact or "",
        } for e in ents])
        st.dataframe(df_ent, use_container_width=True, hide_index=True, height=280)

    st.divider()
    st.subheader("➕ Ajouter un acteur")
    with st.form("form_ent"):
        c1, c2 = st.columns(2)
        with c1:
            nom_e = st.text_input("Nom *")
            sect_e = st.text_input("Secteur")
            type_e = st.selectbox("Type", ["fournisseur","distributeur","importateur","exportateur","logisticien","autre"])
            pays_e = st.selectbox("Pays", config["geo"]["pays_prioritaires"])
        with c2:
            ville_e = st.text_input("Ville")
            taille_e = st.selectbox("Taille", ["petite","moyenne","grande","tres grande"])
            contact_e = st.text_input("Contact")
            notes_e = st.text_area("Notes", height=80)
        if st.form_submit_button("Enregistrer") and nom_e and session:
            ent = Entreprise(nom=nom_e, secteur=sect_e, type=type_e, pays=pays_e,
                             ville=ville_e, taille_estimee=taille_e, contact=contact_e,
                             notes=notes_e, source="Manuel")
            session.add(ent); session.commit()
            st.success(f"✅ {nom_e} ajouté !")
            st.rerun()
