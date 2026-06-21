import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.data_quality.recategorizer import categorize_product

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

import psycopg2

# Etape 1 : creer la colonne si elle n'existe pas
try:
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "ALTER TABLE annonces_informel ADD COLUMN IF NOT EXISTS categorie_detectee VARCHAR(100)"
    )
    cur.close()
    conn.close()
    print("Colonne categorie_detectee OK")
except Exception as e:
    print(f"ALTER TABLE: {e}")

# Etape 2 : remplir par batch via psycopg2 direct
conn = psycopg2.connect(db_url)
cur = conn.cursor()

batch_size = 200
offset = 0
total = 0

while True:
    cur.execute(
        """
        SELECT id, produit, notes_terrain, marque
        FROM annonces_informel
        WHERE categorie_detectee IS NULL
        LIMIT %s OFFSET %s
        """,
        (batch_size, offset)
    )
    rows = cur.fetchall()
    if not rows:
        break

    updates = []
    for row_id, produit, notes_terrain, marque in rows:
        cat = categorize_product(
            produit or '',
            notes_terrain or '',
            marque or ''
        )
        updates.append((cat, row_id))
        total += 1

    cur.executemany(
        "UPDATE annonces_informel SET categorie_detectee = %s WHERE id = %s",
        updates
    )
    conn.commit()
    offset += batch_size
    print(f"Batch {offset//batch_size}: {total} annonces categorisees")

cur.close()
conn.close()
print(f"Done: {total} annonces informel categorisees")
