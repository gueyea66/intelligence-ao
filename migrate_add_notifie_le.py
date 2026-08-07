"""
Migration : colonne notifie_le sur appels_offres.
Trace la date d'envoi dans le digest Telegram pour ne jamais renvoyer le meme AO.
"""
import os
import sys

sys.path.insert(0, '.')
with open('config/.env', encoding='utf-8-sig') as f:
    for l in f:
        l = l.strip()
        if l and not l.startswith('#') and '=' in l:
            k, v = l.split('=', 1); os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'], connect_args={'sslmode': 'require'})

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE appels_offres ADD COLUMN IF NOT EXISTS notifie_le TIMESTAMP"))
    conn.commit()
    print("OK — colonne notifie_le ajoutee (ou deja presente)")
