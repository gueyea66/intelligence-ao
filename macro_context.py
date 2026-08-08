"""
Context anchoring (design Pantheon 08/08/2026) — soude chaque journee de collecte
a son contexte macro du jour. Un prix observe sans son contexte est irrecuperable :
cette table permet aux modeles futurs de reconstruire l'etat du monde au moment
de chaque observation, sans rien refaire.

Tourne chaque jour APRES snapshot_history.py :
1. Cree/complete la ligne macro_daily_context du jour
2. Estampille context_date sur les lignes prix_history et ao_score_history du jour
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None
sys.path.insert(0, '.')
with open('config/.env', encoding='utf-8-sig') as f:
    for l in f:
        l = l.strip()
        if l and not l.startswith('#') and '=' in l:
            k, v = l.split('=', 1); os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'], connect_args={'sslmode': 'require'})

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS macro_daily_context (
            context_date DATE PRIMARY KEY,
            inflation_cpi_pct NUMERIC(8,4),
            inflation_ref_annee INT,
            croissance_pib_pct NUMERIC(8,4),
            pib_par_hab_usd NUMERIC(12,2),
            nb_ao_actifs INT,
            nb_releves_prix_30j INT,
            contexte_json JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    conn.execute(text("ALTER TABLE prix_history ADD COLUMN IF NOT EXISTS context_date DATE"))
    conn.execute(text("ALTER TABLE ao_score_history ADD COLUMN IF NOT EXISTS context_date DATE"))

    # ── derniers indicateurs macro connus (Senegal, World Bank) ──────────────
    def last_indic(label):
        r = conn.execute(text("""
            SELECT valeur, annee FROM donnees_macro
            WHERE (pays ILIKE '%senegal%' OR pays ILIKE '%sénégal%') AND indicateur = :i
            ORDER BY annee DESC LIMIT 1"""), {'i': label}).fetchone()
        return (float(r[0]), int(r[1])) if r else (None, None)

    cpi, cpi_annee = last_indic('Inflation CPI (%)')
    pib_g, _ = last_indic('Croissance PIB (%)')
    pib_hab, _ = last_indic('PIB par habitant (USD)')

    nb_ao = conn.execute(text("SELECT count(*) FROM appels_offres WHERE statut='actif'")).scalar()
    nb_px = conn.execute(text(
        "SELECT count(*) FROM prix_history WHERE date_collecte > NOW() - INTERVAL '30 days'")).scalar()

    # etat marche du jour (extensible : petrole, taux de change... quand captures)
    top_cats = conn.execute(text("""
        SELECT categorie, count(*) FROM appels_offres WHERE statut='actif'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 5""")).fetchall()
    ctx_json = json.dumps({
        'top_categories_ao': [{'categorie': c, 'n': n} for c, n in top_cats],
        'sources_prix_30j': [
            {'source': s, 'n': n} for s, n in conn.execute(text("""
                SELECT source, count(*) FROM prix_history
                WHERE date_collecte > NOW() - INTERVAL '30 days' GROUP BY 1""")).fetchall()
        ],
    })

    conn.execute(text("""
        INSERT INTO macro_daily_context
            (context_date, inflation_cpi_pct, inflation_ref_annee, croissance_pib_pct,
             pib_par_hab_usd, nb_ao_actifs, nb_releves_prix_30j, contexte_json)
        VALUES (CURRENT_DATE, :cpi, :cpia, :pibg, :pibh, :nao, :npx, :ctx)
        ON CONFLICT (context_date) DO UPDATE SET
            nb_ao_actifs = EXCLUDED.nb_ao_actifs,
            nb_releves_prix_30j = EXCLUDED.nb_releves_prix_30j,
            contexte_json = EXCLUDED.contexte_json
    """), {'cpi': cpi, 'cpia': cpi_annee, 'pibg': pib_g, 'pibh': pib_hab,
           'nao': nb_ao, 'npx': nb_px, 'ctx': ctx_json})

    # ── estampiller les observations du jour (et rattraper les non ancrees) ──
    r1 = conn.execute(text("""
        UPDATE prix_history SET context_date = date_collecte::date
        WHERE context_date IS NULL"""))
    r2 = conn.execute(text("""
        UPDATE ao_score_history SET context_date = snapshot_date
        WHERE context_date IS NULL"""))
    conn.commit()

    print(f"Contexte du jour: cpi={cpi} ({cpi_annee}), pib_growth={pib_g}, "
          f"ao_actifs={nb_ao}, releves_30j={nb_px}")
    print(f"Ancrage: prix_history +{r1.rowcount}, ao_score_history +{r2.rowcount}")
