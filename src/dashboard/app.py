"""
Dashboard Streamlit — Intelligence Commerciale Afrique de l'Ouest
4 onglets : Marché | Appels d'Offres | Informel | Réseau

Lancer : streamlit run src/dashboard/app.py
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
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


# ── Config page ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Intelligence Commerciale AO",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.metric-card {
    background: linear-gradient(135deg, #1565c0, #0d47a1);
    border-radius: 12px; padding: 16px; color: white; margin: 4px;
}
.metric-val { font-size: 2rem; font-weight: bold; }
.metric-lbl { font-size: 0.85rem; opacity: 0.8; }
.priority-high { background: #ffebee; border-left: 4px solid #d32f2f; padding: 8px; border-radius: 4px; }
.priority-med  { background: #fff8e1; border-left: 4px solid #f57c00; padding: 8px; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_config():
    return load_config()

@st.cache_resource
def get_db_session():
    return get_session(get_config())


config  = get_config()
session = get_db_session()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌍 Intel Commerciale")
    st.caption("Afrique de l'Ouest — MVP")
    st.divider()

    stats = stats_summary(config)

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Produits", f"{stats['nb_produits']:,}")
        st.metric("AOs actifs", stats["nb_aos_actifs"])
    with col_b:
        st.metric("🔴 Prioritaires", stats["ao_prioritaires"])
        st.metric("Informel", stats["nb_informel"])

    st.divider()

    derniere_collecte = session.query(Produit.date_collecte)\
        .order_by(Produit.date_collecte.desc()).first()
    if derniere_collecte:
        st.caption(f"Dernière collecte : {derniere_collecte[0].strftime('%d/%m %H:%M')}")

    st.divider()
    if st.button("🔄 Rafraîchir"):
        st.cache_resource.clear()
        st.rerun()

    st.divider()
    st.caption("Commandes rapides :")
    st.code("python main.py scrape\npython main.py score\npython main.py export", language="bash")


# ── Onglets ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📦 Vue Marché",
    "📋 Appels d'Offres",
    "🏪 Marché Informel",
    "🤝 Réseau",
])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1 — VUE MARCHÉ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    st.header("📦 Catalogue Produits")

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    total_produits = session.query(Produit).count()
    nb_sources     = len(_get_distinct(session, Produit.source))
    nb_categories  = len(_get_distinct(session, Produit.categorie_1))
    nb_marques     = len(_get_distinct(session, Produit.marque))
    k1.metric("Total produits", f"{total_produits:,}")
    k2.metric("Sources actives", nb_sources)
    k3.metric("Catégories", nb_categories)
    k4.metric("Marques", nb_marques)

    st.divider()

    # Filtres
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        filtre_cat = st.selectbox("Catégorie", ["Toutes"] + _get_distinct(session, Produit.categorie_1))
    with col2:
        filtre_marque = st.selectbox("Marque", ["Toutes"] + _get_distinct(session, Produit.marque))
    with col3:
        filtre_source = st.selectbox("Source", ["Toutes"] + _get_distinct(session, Produit.source))
    with col4:
        filtre_promo = st.checkbox("Promotions seulement")

    q = session.query(Produit)
    if filtre_cat != "Toutes":    q = q.filter(Produit.categorie_1 == filtre_cat)
    if filtre_marque != "Toutes": q = q.filter(Produit.marque == filtre_marque)
    if filtre_source != "Toutes": q = q.filter(Produit.source == filtre_source)
    if filtre_promo:              q = q.filter(Produit.promotion == True)

    produits = q.order_by(Produit.date_collecte.desc()).limit(1000).all()

    if produits:
        df = pd.DataFrame([{
            "Marque":      p.marque or "",
            "Modèle":      (p.modele or "")[:60],
            "Catégorie":   p.categorie_1 or "",
            "Prix (XOF)":  p.prix_actuel,
            "Barré (XOF)": p.prix_barre,
            "Promo":       "✅" if p.promotion else "",
            "Source":      p.source,
            "Pays":        p.pays,
            "Date":        p.date_collecte.strftime("%d/%m/%Y") if p.date_collecte else "",
        } for p in produits])

        st.dataframe(df, use_container_width=True, hide_index=True, height=350)
        st.caption(f"{len(produits)} produits affichés (max 1000)")

        st.divider()
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.subheader("Prix moyen par catégorie (XOF)")
            df_cat = df[df["Prix (XOF)"].notna() & (df["Prix (XOF)"] > 0) & (df["Prix (XOF)"] < 10_000_000)]
            if not df_cat.empty:
                prix_moy = df_cat.groupby("Catégorie")["Prix (XOF)"].mean().sort_values(ascending=False).head(10)
                st.bar_chart(prix_moy)

        with col_g2:
            st.subheader("Top 10 marques (volume)")
            top_marques = df["Marque"].value_counts().head(10)
            if not top_marques.empty:
                st.bar_chart(top_marques)

        st.subheader("Répartition par source")
        src_count = df["Source"].value_counts()
        st.bar_chart(src_count)

    else:
        st.info("Aucun produit. Lancer : `python main.py scrape --source ecommerce`")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2 — APPELS D'OFFRES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.header("📋 Appels d'Offres")

    # KPIs AO
    k1, k2, k3, k4, k5 = st.columns(5)
    total_aos  = session.query(AppelOffre).count()
    actifs_aos = session.query(AppelOffre).filter(AppelOffre.date_limite >= datetime.utcnow()).count()
    hauts      = session.query(AppelOffre).filter(AppelOffre.score >= config["scoring"]["seuils"]["priorite_haute"]).count()
    surveiller = session.query(AppelOffre).filter(
        AppelOffre.score >= config["scoring"]["seuils"]["a_surveiller"],
        AppelOffre.score < config["scoring"]["seuils"]["priorite_haute"]
    ).count()
    non_scores = session.query(AppelOffre).filter(AppelOffre.score.is_(None)).count()

    k1.metric("Total AOs", total_aos)
    k2.metric("Actifs", actifs_aos)
    k3.metric("🔴 HAUTE priorité", hauts)
    k4.metric("🟡 À surveiller", surveiller)
    k5.metric("Non scorés", non_scores)

    if non_scores > 0:
        st.warning(f"⚠️ {non_scores} AOs non scorés. Lancer : `python main.py score`")

    st.divider()

    # Filtres
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        filtre_pays_ao = st.selectbox("Pays", ["Tous"] + _get_distinct(session, AppelOffre.pays), key="ao_pays")
    with col2:
        filtre_source_ao = st.selectbox("Source", ["Toutes"] + _get_distinct(session, AppelOffre.source), key="ao_src")
    with col3:
        score_min = st.slider("Score minimum", 0, 100, 0)
    with col4:
        actifs_seulement = st.checkbox("Actifs seulement", value=True)

    q_ao = session.query(AppelOffre)
    if filtre_pays_ao != "Tous":      q_ao = q_ao.filter(AppelOffre.pays == filtre_pays_ao)
    if filtre_source_ao != "Toutes":  q_ao = q_ao.filter(AppelOffre.source == filtre_source_ao)
    if score_min > 0:                 q_ao = q_ao.filter(AppelOffre.score >= score_min)
    if actifs_seulement:              q_ao = q_ao.filter(AppelOffre.date_limite >= datetime.utcnow())

    aos = q_ao.order_by(AppelOffre.score.desc().nullslast()).limit(500).all()

    if aos:
        rows = []
        for ao in aos:
            score = ao.score or 0
            niveau = "🔴 HAUTE" if score >= 70 else ("🟡 SURVEILLER" if score >= 40 else "⚪ ARCHIVÉ")
            rows.append({
                "Score":          f"{score:.0f}" if score else "—",
                "Niveau":         niveau,
                "Source":         ao.source,
                "Référence":      ao.reference or "",
                "Objet":          (ao.objet or "")[:80],
                "Entité":         ao.entite or "",
                "Pays":           ao.pays or "",
                "Budget":         f"{ao.budget_estime:,.0f} {ao.devise}" if ao.budget_estime else "—",
                "Jours":          ao.jours_restants,
                "Positionnement": ao.positionnement or "—",
            })

        df_ao = pd.DataFrame(rows)
        st.dataframe(df_ao, use_container_width=True, hide_index=True, height=350)
        st.caption(f"{len(aos)} AOs affichés")

        # Graphiques AO
        st.divider()
        col_g1, col_g2, col_g3 = st.columns(3)

        with col_g1:
            st.subheader("Distribution scores")
            scores = [ao.score for ao in aos if ao.score is not None]
            if scores:
                df_s = pd.DataFrame({"Score": scores})
                bins = pd.cut(df_s["Score"], bins=[0,40,70,100], labels=["⚪ <40","🟡 40-70","🔴 >70"])
                st.bar_chart(bins.value_counts())

        with col_g2:
            st.subheader("AOs par pays")
            pays_count = df_ao["Pays"].value_counts().head(10)
            if not pays_count.empty:
                st.bar_chart(pays_count)

        with col_g3:
            st.subheader("AOs par source")
            src_count_ao = df_ao["Source"].value_counts()
            if not src_count_ao.empty:
                st.bar_chart(src_count_ao)

        # Détail AO
        st.divider()
        st.subheader("Détail AO")
        refs = [ao.reference for ao in aos if ao.reference]
        if refs:
            ref_sel = st.selectbox("Sélectionner un AO", refs[:50])
            ao_sel  = next((a for a in aos if a.reference == ref_sel), None)
            if ao_sel:
                with st.expander("Détail complet", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write(f"**Référence :** {ao_sel.reference}")
                        st.write(f"**Source :** {ao_sel.source}")
                        st.write(f"**Entité :** {ao_sel.entite or '—'}")
                        st.write(f"**Pays :** {ao_sel.pays}")
                    with c2:
                        st.write(f"**Score :** {ao_sel.score}")
                        st.write(f"**Catégorie :** {ao_sel.categorie}")
                        st.write(f"**Budget :** {ao_sel.budget_estime:,.0f} {ao_sel.devise}" if ao_sel.budget_estime else "**Budget :** —")
                        st.write(f"**Date limite :** {ao_sel.date_limite.strftime('%d/%m/%Y') if ao_sel.date_limite else '—'}")
                    with c3:
                        st.write(f"**Jours restants :** {ao_sel.jours_restants}")
                        st.write(f"**Positionnement :** {ao_sel.positionnement or '—'}")
                        if ao_sel.url_source:
                            st.markdown(f"[🔗 Voir l'AO original]({ao_sel.url_source})")

                    st.write("**Objet :**", ao_sel.objet or "—")

                    if ao_sel.detail_scores:
                        try:
                            detail = json.loads(ao_sel.detail_scores)
                            st.subheader("Détail des scores par critère")
                            df_detail = pd.DataFrame(
                                list(detail.items()), columns=["Critère", "Score"]
                            ).set_index("Critère")
                            st.bar_chart(df_detail)
                        except Exception:
                            pass
    else:
        st.info("Aucun AO. Lancer : `python main.py scrape --source ao && python main.py score`")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3 — MARCHÉ INFORMEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.header("🏪 Marché Informel")

    # KPIs
    k1, k2, k3 = st.columns(3)
    total_inf  = session.query(AnnoncInformel).count()
    nb_zones   = len(_get_distinct(session, AnnoncInformel.vendeur_zone))
    avec_prix  = session.query(AnnoncInformel).filter(AnnoncInformel.prix_unitaire.isnot(None)).count()
    k1.metric("Total annonces", total_inf)
    k2.metric("Zones couvertes", nb_zones)
    k3.metric("Avec prix", avec_prix)

    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        filtre_zone = st.selectbox("Zone", ["Toutes"] + _get_distinct(session, AnnoncInformel.vendeur_zone))
    with col2:
        filtre_type_inf = st.selectbox("Type", ["Tous", "offre", "demande"])
    with col3:
        recherche = st.text_input("🔍 Recherche produit", "")

    q_inf = session.query(AnnoncInformel)
    if filtre_zone != "Toutes":       q_inf = q_inf.filter(AnnoncInformel.vendeur_zone == filtre_zone)
    if filtre_type_inf != "Tous":     q_inf = q_inf.filter(AnnoncInformel.type == filtre_type_inf)
    if recherche:                     q_inf = q_inf.filter(AnnoncInformel.produit.ilike(f"%{recherche}%"))

    annonces = q_inf.order_by(AnnoncInformel.date_collecte.desc()).limit(500).all()

    if annonces:
        df_inf = pd.DataFrame([{
            "Source":      a.source,
            "Produit":     (a.produit or "")[:60],
            "Prix (XOF)":  a.prix_unitaire,
            "Zone":        a.vendeur_zone or "",
            "Type":        a.type or "",
            "Contact":     "✅" if a.contact_disponible else "❌",
            "Date":        a.date_collecte.strftime("%d/%m/%Y") if a.date_collecte else "",
        } for a in annonces])

        st.dataframe(df_inf, use_container_width=True, hide_index=True, height=300)

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("Activité par zone")
            zone_count = df_inf["Zone"].value_counts()
            if not zone_count.empty:
                st.bar_chart(zone_count)
        with col_g2:
            st.subheader("Activité par source")
            src_inf = df_inf["Source"].value_counts()
            if not src_inf.empty:
                st.bar_chart(src_inf)

    else:
        st.info("Aucune annonce informel. Activer Jotay/CoinAfrique dans config.yaml et lancer `python main.py scrape --source informel`")

    # Fiches marchés
    st.divider()
    st.subheader("📍 Fiches marchés")
    zones_cfg = config.get("geo", {}).get("zones_informel", [])
    cols_m = st.columns(min(len(zones_cfg), 3))
    for i, z in enumerate(zones_cfg):
        with cols_m[i % 3]:
            nb_ann = sum(1 for a in annonces if a.vendeur_zone == z.get("nom", ""))
            puissance = z.get("puissance_estimee", "")
            emoji = "🔥" if puissance == "très haute" else ("⚡" if puissance == "haute" else "📍")
            st.markdown(f"""
**{emoji} {z.get('nom', '')}** — {z.get('ville', '')}
Spécialités : {', '.join(z.get('specialites', []))}
Puissance : *{puissance}*
Annonces actives : **{nb_ann}**
""")

    # Saisie terrain manuelle
    st.divider()
    st.subheader("📝 Saisie terrain manuelle")
    with st.form("form_informel"):
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            produit_t   = st.text_input("Produit")
            marque_t    = st.text_input("Marque")
            zone_t      = st.selectbox("Zone", [z.get("nom", "") for z in zones_cfg] + ["Autre"])
            type_t      = st.selectbox("Type", ["offre", "demande"])
        with col_f2:
            quantite_t  = st.number_input("Quantité", min_value=1, value=1)
            prix_t      = st.number_input("Prix unitaire (XOF)", min_value=0, value=0)
            contact_t   = st.checkbox("Contact disponible")
            notes_t     = st.text_area("Notes terrain")

        if st.form_submit_button("✅ Enregistrer") and produit_t:
            from src.database.models import AnnoncInformel as AI
            ann = AI(
                source="Terrain",
                date_collecte=datetime.utcnow(),
                type=type_t,
                produit=produit_t,
                marque=marque_t,
                quantite_disponible=quantite_t,
                prix_unitaire=prix_t if prix_t > 0 else None,
                devise="XOF",
                vendeur_zone=zone_t,
                contact_disponible=contact_t,
                notes_terrain=notes_t,
            )
            session.add(ann)
            session.commit()
            st.success(f"✅ {produit_t} enregistré !")
            st.rerun()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 4 — RÉSEAU
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab4:
    st.header("🤝 Réseau Fournisseurs & Acteurs")

    # KPIs réseau
    total_ent = session.query(Entreprise).count()
    k1, k2, k3 = st.columns(3)
    k1.metric("Entreprises", total_ent)
    k2.metric("Pays couverts", len(_get_distinct(session, Entreprise.pays)))
    k3.metric("Secteurs", len(_get_distinct(session, Entreprise.secteur)))

    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        filtre_type_ent = st.selectbox("Type", ["Tous"] + _get_distinct(session, Entreprise.type))
    with col2:
        filtre_secteur = st.selectbox("Secteur", ["Tous"] + _get_distinct(session, Entreprise.secteur))
    with col3:
        filtre_pays_ent = st.selectbox("Pays", ["Tous"] + _get_distinct(session, Entreprise.pays), key="ent_pays")

    q_ent = session.query(Entreprise)
    if filtre_type_ent != "Tous":  q_ent = q_ent.filter(Entreprise.type == filtre_type_ent)
    if filtre_secteur != "Tous":   q_ent = q_ent.filter(Entreprise.secteur == filtre_secteur)
    if filtre_pays_ent != "Tous":  q_ent = q_ent.filter(Entreprise.pays == filtre_pays_ent)

    entreprises = q_ent.order_by(Entreprise.nom).limit(500).all()

    if entreprises:
        df_ent = pd.DataFrame([{
            "Nom":      e.nom,
            "Secteur":  e.secteur or "",
            "Type":     e.type or "",
            "Pays":     e.pays or "",
            "Ville":    e.ville or "",
            "Taille":   e.taille_estimee or "",
            "Contact":  e.contact or "",
            "Source":   e.source or "",
        } for e in entreprises])

        st.dataframe(df_ent, use_container_width=True, hide_index=True, height=300)

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("Par type")
            st.bar_chart(df_ent["Type"].value_counts())
        with col_g2:
            st.subheader("Par secteur")
            st.bar_chart(df_ent["Secteur"].value_counts().head(10))

    else:
        st.info("Aucune entreprise. À enrichir via le formulaire ci-dessous ou via scraping annuaires.")

    st.divider()
    st.subheader("➕ Ajouter une entreprise")
    with st.form("form_entreprise"):
        c1, c2 = st.columns(2)
        with c1:
            nom_e     = st.text_input("Nom de l'entreprise *")
            secteur_e = st.text_input("Secteur")
            type_e    = st.selectbox("Type", ["fournisseur", "distributeur", "importateur", "exportateur", "logisticien", "autre"])
            pays_e    = st.selectbox("Pays", config["geo"]["pays_prioritaires"])
        with c2:
            ville_e   = st.text_input("Ville")
            taille_e  = st.selectbox("Taille estimée", ["petite", "moyenne", "grande", "très grande"])
            contact_e = st.text_input("Contact (email / tél)")
            notes_e   = st.text_area("Notes")

        if st.form_submit_button("Enregistrer") and nom_e:
            from src.database.models import Entreprise as Ent
            ent = Ent(nom=nom_e, secteur=secteur_e, type=type_e, pays=pays_e,
                      ville=ville_e, taille_estimee=taille_e, contact=contact_e,
                      notes=notes_e, source="Manuel")
            session.add(ent)
            session.commit()
            st.success(f"✅ {nom_e} ajouté !")
            st.rerun()

    # Import CSV entreprises
    st.divider()
    st.subheader("📂 Import CSV entreprises")
    uploaded = st.file_uploader("CSV avec colonnes: nom, secteur, type, pays, ville, contact", type="csv")
    if uploaded:
        try:
            df_upload = pd.read_csv(uploaded)
            nb_import = 0
            for _, row in df_upload.iterrows():
                from src.database.models import Entreprise as Ent
                ent = Ent(
                    nom=str(row.get("nom", "")),
                    secteur=str(row.get("secteur", "")),
                    type=str(row.get("type", "autre")),
                    pays=str(row.get("pays", "Sénégal")),
                    ville=str(row.get("ville", "")),
                    contact=str(row.get("contact", "")),
                    source="Import CSV",
                )
                session.add(ent)
                nb_import += 1
            session.commit()
            st.success(f"✅ {nb_import} entreprises importées !")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur import : {e}")
