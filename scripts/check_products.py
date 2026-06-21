import os
from sqlalchemy import create_engine, text

e = create_engine(os.environ["DATABASE_URL"])
with e.connect() as conn:
    rows = conn.execute(text(
        "SELECT categorie_1, categorie_2, marque, modele, description, source "
        "FROM produits WHERE categorie_1 = 'Divers' LIMIT 10"
    )).fetchall()
    print("=== EXEMPLE PRODUITS DIVERS ===")
    for r in rows:
        print(f"  cat2={r[1]} | marque={r[2]} | modele={str(r[3])[:30]} | desc={str(r[4])[:60]} | src={r[5]}")

    # Stats sources
    src_stats = conn.execute(text(
        "SELECT source, categorie_1, COUNT(*) as nb FROM produits "
        "GROUP BY source, categorie_1 ORDER BY nb DESC LIMIT 20"
    )).fetchall()
    print("\n=== STATS SOURCE x CATEGORIE ===")
    for r in src_stats:
        print(f"  {r[0]} | {r[1]} | {r[2]}")
