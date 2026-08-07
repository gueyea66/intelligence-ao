"""
Fix date quality:
1. Marque comme 'expire' tous les AOs dont date_limite < aujourd'hui
2. Met date_limite = NULL pour MarchesDuSenegal (date inconnue, pas de fausse date)
3. Recalcule jours_restants partout
"""
import os, sys
sys.path.insert(0, '.')
with open('config/.env', encoding='utf-8-sig') as f:
    for l in f:
        l = l.strip()
        if l and not l.startswith('#') and '=' in l:
            k, v = l.split('=', 1); os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'], connect_args={'sslmode': 'require'})

with engine.connect() as conn:

    # 0. Normaliser les statuts : 'nouveau' devient 'actif' pour entrer dans
    #    le pipeline digest/scoring comme les autres sources
    r0 = conn.execute(text("""
        UPDATE appels_offres
        SET statut = 'actif'
        WHERE statut = 'nouveau'
    """))
    print(f"Nouveaux normalises en actif: {r0.rowcount}")

    # 1. Marquer expires (date_limite dans le passe)
    r = conn.execute(text("""
        UPDATE appels_offres
        SET statut = 'historique'
        WHERE date_limite < NOW() AND statut = 'actif'
    """))
    print(f"Marques expire: {r.rowcount}")

    # 2. MarchesDuSenegal : date_limite etait un defaut (+30j), on la met a NULL
    #    On detecte par jours_restants entre 28 et 32 au moment de l'insertion
    #    Plus fiable : mettre a NULL TOUTES les dates MarchesDuSenegal
    #    car on n'a pas pu parser une vraie date
    r2 = conn.execute(text("""
        UPDATE appels_offres
        SET date_limite = NULL,
            jours_restants = NULL
        WHERE source = 'MarchesDuSenegal'
          AND statut NOT IN ('expire', 'historique')
    """))
    print(f"MarchesDuSenegal dates remises a NULL: {r2.rowcount}")

    # 2b. Les AOs sans date limite ne peuvent pas expirer par la regle 1 :
    #     au-dela de 30 jours apres collecte, ils sont perimes en pratique
    r2b = conn.execute(text("""
        UPDATE appels_offres
        SET statut = 'historique'
        WHERE date_limite IS NULL
          AND statut = 'actif'
          AND date_collecte < NOW() - INTERVAL '30 days'
    """))
    print(f"Sans date >30j passes en historique: {r2b.rowcount}")

    # 3. Recalculer jours_restants pour les AOs avec vraie date
    r3 = conn.execute(text("""
        UPDATE appels_offres
        SET jours_restants = GREATEST(0, EXTRACT(DAY FROM (date_limite - NOW()))::int)
        WHERE date_limite IS NOT NULL AND statut = 'actif'
    """))
    print(f"Jours recalcules: {r3.rowcount}")

    conn.commit()

    # Verification finale
    print()
    rows = conn.execute(text("""
        SELECT statut, source,
               COUNT(*) as nb,
               SUM(CASE WHEN date_limite IS NULL THEN 1 ELSE 0 END) as sans_date,
               MIN(date_limite), MAX(date_limite)
        FROM appels_offres
        GROUP BY statut, source
        ORDER BY statut, nb DESC
    """)).fetchall()
    print("=== Etat final ===")
    for r in rows:
        print(f"  {r[0]:8} | {r[1]:25} | nb={r[2]:3} | sans_date={r[3]} | {r[4]} -> {r[5]}")
