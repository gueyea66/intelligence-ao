import os
from sqlalchemy import create_engine, text

e = create_engine(os.environ["DATABASE_URL"])
with e.connect() as c:
    rows = c.execute(text(
        "SELECT categorie_1, COUNT(*) as nb FROM produits GROUP BY categorie_1 ORDER BY nb DESC LIMIT 20"
    )).fetchall()
    total = sum(r[1] for r in rows)
    print(f"Total: {total}")
    for r in rows:
        pct = 100 * r[1] // total
        print(f"  {r[0] or 'NULL'}: {r[1]} ({pct}%)")
