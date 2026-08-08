"""
Snapshots quotidiens — preserve l'historique pour les algorithmes futurs.
Regle : jamais d'ecrasement destructif. Ce qu'on ne snapshotte pas aujourd'hui
est perdu pour toujours.

1. ao_score_history : score + statut de chaque AO chaque jour (le scoring ML
   ecrase la colonne score ; sans ce snapshot, aucune etude retrospective possible)
2. prix_history : releve de prix par produit (serie temporelle marche informel/formel)

Idempotent : une ligne par (objet, jour) — relancable sans doublons.
"""
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
    # ── 1. Historique des scores AO ──────────────────────────────────────────
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ao_score_history (
            id BIGSERIAL PRIMARY KEY,
            ao_id VARCHAR(64) NOT NULL,
            score DOUBLE PRECISION,
            statut VARCHAR(20),
            jours_restants INTEGER,
            snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
            UNIQUE (ao_id, snapshot_date)
        )
    """))
    r = conn.execute(text("""
        INSERT INTO ao_score_history (ao_id, score, statut, jours_restants, snapshot_date)
        SELECT id, score, statut, jours_restants, CURRENT_DATE
        FROM appels_offres
        ON CONFLICT (ao_id, snapshot_date) DO NOTHING
    """))
    print(f"ao_score_history: +{r.rowcount} snapshots")

    # ── 2. Series de prix (produits -> prix_history) ─────────────────────────
    # une ligne par produit et par jour de collecte, jamais reecrite
    r = conn.execute(text("""
        INSERT INTO prix_history (produit_ref, source, categorie_std, prix, date_collecte)
        SELECT p.id, p.source, p.categorie_1, p.prix_actuel, p.date_collecte
        FROM produits p
        WHERE p.prix_actuel > 0
          AND NOT EXISTS (
            SELECT 1 FROM prix_history h
            WHERE h.produit_ref = p.id
              AND h.date_collecte::date = p.date_collecte::date
          )
    """))
    print(f"prix_history: +{r.rowcount} releves")

    conn.commit()

    # ── etat des series ──────────────────────────────────────────────────────
    r = conn.execute(text("""
        SELECT count(*), count(DISTINCT snapshot_date), min(snapshot_date), max(snapshot_date)
        FROM ao_score_history""")).fetchone()
    print(f"Serie scores AO : {r[0]} lignes, {r[1]} jours ({r[2]} -> {r[3]})")
    r = conn.execute(text("""
        SELECT count(*), count(DISTINCT date_collecte::date), min(date_collecte)::date, max(date_collecte)::date
        FROM prix_history""")).fetchone()
    print(f"Serie prix     : {r[0]} releves, {r[1]} jours ({r[2]} -> {r[3]})")
