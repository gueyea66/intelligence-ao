"""
Moteur d'alertes v1 — design Pantheon (run scientifique 08/08/2026).
Regle d'or : aucun LLM, tout chiffre sort de SQL/scipy verifiable.

Detecteur 1 — PRIX_ANOMALIE : z-score winsorise par (categorie, source),
  fenetre 28 j. Baseline winsorisee a 5% des deux queues. Seuil adaptatif :
  |z| > 2.0 si n < 30, |z| > 2.5 si n >= 30 (queues epaisses petits echantillons).
  Condition falsifiante (board) : si faux positifs > 30% sur 4 semaines -> seuil 3.0.

Detecteur 2 — SPREAD_ARBITRAGE : ecart formel/informel par famille de produits.
  Spread = (mediane_informel - moyenne_formel) / moyenne_formel * 100.
  Mediane cote informel (queues epaisses : negociation, etat, urgence),
  moyenne cote formel (prix catalogue). Significativite : Mann-Whitney U,
  alerte uniquement si p < 0.10 ET |spread| > 15%.

Dedup : pas de nouvelle alerte si une alerte identique (type+categorie+source)
existe depuis moins de 7 jours. Feedback operateur via operator_validated /
false_positive (boucle d'apprentissage, futur dataset).
"""
import os
import sys
from datetime import datetime

import numpy as np
from scipy.stats import mannwhitneyu
from scipy.stats.mstats import winsorize

sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None
sys.path.insert(0, '.')
with open('config/.env', encoding='utf-8-sig') as f:
    for l in f:
        l = l.strip()
        if l and not l.startswith('#') and '=' in l:
            k, v = l.split('=', 1); os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'], connect_args={'sslmode': 'require'})

WINDOW_DAYS = 28
MIN_N_BASELINE = 8
SPREAD_MIN_PCT = 15.0
SPREAD_MAX_P = 0.10
DEDUP_DAYS = 7

# familles comparables formel (Jumia/Auchan) vs informel (Expat/CoinAfrique)
FAMILLES_SPREAD = {
    'telephones': {
        'formel': [('jumia_sn', 'telephones'), ('auchan_sn', 'telephones')],
        'informel': [('expat_dakar', 'telephones'), ('coinafrique', 'telephones')],
    },
    'alimentation': {
        'formel': [('jumia_sn', 'alimentation'), ('auchan_sn', 'alimentation')],
        'informel': [('expat_dakar', 'produits-alimentaires'), ('expat_dakar', 'poulets-viandes')],
    },
    'electromenager': {
        'formel': [('jumia_sn', 'Électroménager'), ('auchan_sn', 'electromenager')],
        'informel': [('expat_dakar', 'refrigerateurs-congelateurs'), ('expat_dakar', 'machines-a-laver'),
                     ('expat_dakar', 'micro-ondes'), ('expat_dakar', 'cuisinieres-fours'),
                     ('expat_dakar', 'autre-electromenager'), ('expat_dakar', 'machines-a-cafe')],
    },
}


def ensure_table(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS alertes_marche (
            id BIGSERIAL PRIMARY KEY,
            alert_type VARCHAR(30) NOT NULL,
            severity VARCHAR(10) NOT NULL DEFAULT 'warning',
            categorie VARCHAR(60),
            source VARCHAR(60),
            z_score NUMERIC(8,3),
            spread_pct NUMERIC(8,2),
            p_value NUMERIC(8,5),
            prix_observe BIGINT,
            prix_baseline BIGINT,
            n_obs INT,
            texte_fr TEXT NOT NULL,
            detail_json JSONB,
            context_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT NOW(),
            digest_envoye_le TIMESTAMP,
            operator_validated BOOLEAN,
            false_positive BOOLEAN
        )
    """))


def deja_alerte(conn, alert_type, categorie, source):
    return conn.execute(text("""
        SELECT 1 FROM alertes_marche
        WHERE alert_type = :t AND categorie = :c AND COALESCE(source,'') = COALESCE(:s,'')
          AND created_at > NOW() - make_interval(days => :d)
        LIMIT 1
    """), {'t': alert_type, 'c': categorie, 's': source, 'd': DEDUP_DAYS}).fetchone() is not None


def inserer(conn, **kw):
    conn.execute(text("""
        INSERT INTO alertes_marche
            (alert_type, severity, categorie, source, z_score, spread_pct, p_value,
             prix_observe, prix_baseline, n_obs, texte_fr, context_date)
        VALUES (:alert_type, :severity, :categorie, :source, :z_score, :spread_pct,
                :p_value, :prix_observe, :prix_baseline, :n_obs, :texte_fr, CURRENT_DATE)
    """), {k: kw.get(k) for k in ('alert_type', 'severity', 'categorie', 'source', 'z_score',
                                  'spread_pct', 'p_value', 'prix_observe', 'prix_baseline',
                                  'n_obs', 'texte_fr')})


def detecteur_zscore(conn):
    """Anomalies de prix du jour vs baseline 28 j winsorisee, par (categorie, source)."""
    n_alertes = 0
    groupes = conn.execute(text("""
        SELECT categorie_std, source FROM prix_history
        WHERE date_collecte > NOW() - make_interval(days => :w)
        GROUP BY 1, 2 HAVING count(*) >= :n
    """), {'w': WINDOW_DAYS, 'n': MIN_N_BASELINE}).fetchall()

    for cat, src in groupes:
        rows = conn.execute(text("""
            SELECT prix, date_collecte::date FROM prix_history
            WHERE categorie_std = :c AND source = :s
              AND date_collecte > NOW() - make_interval(days => :w)
              AND prix > 0
        """), {'c': cat, 's': src, 'w': WINDOW_DAYS}).fetchall()
        jour = [float(p) for p, d in rows if d == datetime.now().date()]
        baseline = [float(p) for p, _ in rows]
        if len(jour) == 0 or len(baseline) < MIN_N_BASELINE:
            continue

        wb = winsorize(np.array(baseline), limits=[0.05, 0.05])
        mu, sigma = float(np.mean(wb)), float(np.std(wb, ddof=1))
        if sigma <= 0:
            continue
        seuil = 2.0 if len(baseline) < 30 else 2.5

        # observation extreme du jour (la plus deviante)
        z_max, prix_max = 0.0, None
        for p in jour:
            z = (p - mu) / sigma
            if abs(z) > abs(z_max):
                z_max, prix_max = z, p
        if abs(z_max) <= seuil:
            continue
        if deja_alerte(conn, 'PRIX_ANOMALIE', cat, src):
            continue

        sens = "au-dessus" if z_max > 0 else "en dessous"
        inserer(conn,
                alert_type='PRIX_ANOMALIE',
                severity='critical' if abs(z_max) > 3.5 else 'warning',
                categorie=cat, source=src, z_score=round(z_max, 3),
                prix_observe=int(prix_max), prix_baseline=int(mu), n_obs=len(baseline),
                texte_fr=(f"{cat} ({src}) : prix observe {int(prix_max):,} FCFA, "
                          f"{abs(z_max):.1f} ecarts-types {sens} de la base 28 j "
                          f"({int(mu):,} FCFA, n={len(baseline)})").replace(',', ' '))
        n_alertes += 1
    return n_alertes


def detecteur_spread(conn):
    """Ecart formel/informel par famille + test Mann-Whitney U."""
    n_alertes = 0

    def prix(paires):
        vals = []
        for src, cat in paires:
            rows = conn.execute(text("""
                SELECT prix FROM prix_history
                WHERE source = :s AND categorie_std = :c AND prix > 0
                  AND date_collecte > NOW() - make_interval(days => :w)
            """), {'s': src, 'c': cat, 'w': WINDOW_DAYS}).fetchall()
            vals.extend(float(r[0]) for r in rows)
        return vals

    for famille, cfg in FAMILLES_SPREAD.items():
        formel, informel = prix(cfg['formel']), prix(cfg['informel'])
        if len(formel) < 5 or len(informel) < 5:
            continue
        moy_f = float(np.mean(winsorize(np.array(formel), limits=[0.05, 0.05])))
        med_i = float(np.median(informel))
        if moy_f <= 0:
            continue
        spread = (med_i - moy_f) / moy_f * 100.0
        stat, p = mannwhitneyu(informel, formel, alternative='two-sided')
        if abs(spread) <= SPREAD_MIN_PCT or p >= SPREAD_MAX_P:
            continue
        if deja_alerte(conn, 'SPREAD_ARBITRAGE', famille, None):
            continue

        sens = "moins cher" if spread < 0 else "plus cher"
        inserer(conn,
                alert_type='SPREAD_ARBITRAGE', severity='warning',
                categorie=famille, source=None,
                spread_pct=round(spread, 2), p_value=round(float(p), 5),
                prix_observe=int(med_i), prix_baseline=int(moy_f),
                n_obs=len(formel) + len(informel),
                texte_fr=(f"{famille} : l'informel est {abs(spread):.0f}% {sens} que le formel "
                          f"(mediane rue {int(med_i):,} vs catalogue {int(moy_f):,} FCFA, "
                          f"p={p:.3f}, n={len(informel)}+{len(formel)})").replace(',', ' '))
        n_alertes += 1
    return n_alertes


if __name__ == '__main__':
    with engine.connect() as conn:
        ensure_table(conn)
        nz = detecteur_zscore(conn)
        ns = detecteur_spread(conn)
        conn.commit()
        total = conn.execute(text("SELECT count(*) FROM alertes_marche")).scalar()
        en_attente = conn.execute(text(
            "SELECT count(*) FROM alertes_marche WHERE digest_envoye_le IS NULL")).scalar()
        print(f"Alertes nouvelles: z-score={nz}, spread={ns} | total base={total}, en attente digest={en_attente}")
