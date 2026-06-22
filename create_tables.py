"""Crée les tables manquantes dans Supabase."""
import os, sys
from pathlib import Path

env_path = Path(__file__).parent / "config" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    sys.exit("DATABASE_URL introuvable dans config/.env")

from sqlalchemy import create_engine, text

engine = create_engine(db_url, connect_args={"sslmode": "require", "connect_timeout": 10})

DDL = [
    """CREATE TABLE IF NOT EXISTS discussions_sociales (
        id SERIAL PRIMARY KEY,
        plateforme VARCHAR(50), canal VARCHAR(255), canal_id VARCHAR(255),
        message_id VARCHAR(255), texte_brut TEXT, langue VARCHAR(10),
        date_publication TIMESTAMP, date_collecte TIMESTAMP DEFAULT NOW(),
        auteur_hash VARCHAR(64), sentiment VARCHAR(20), score_sentiment FLOAT,
        topics JSONB, pain_points JSONB, prix_mentionnes JSONB,
        entites JSONB, mots_cles JSONB, type_message VARCHAR(50),
        categorie_produit VARCHAR(100), contient_prix BOOLEAN DEFAULT FALSE,
        contient_contact BOOLEAN DEFAULT FALSE, est_spam BOOLEAN DEFAULT FALSE,
        traite BOOLEAN DEFAULT FALSE,
        UNIQUE(plateforme, canal_id, message_id)
    )""",
    """CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id SERIAL PRIMARY KEY,
        chunk_type VARCHAR(50) NOT NULL, sujet VARCHAR(200) NOT NULL,
        zone VARCHAR(100) DEFAULT 'Dakar', periode VARCHAR(50),
        contenu TEXT NOT NULL, metadata JSONB DEFAULT '{}',
        sources_count INT DEFAULT 0, confidence FLOAT DEFAULT 0.5,
        created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(chunk_type, sujet, zone, periode)
    )""",
]

with engine.connect() as conn:
    for ddl in DDL:
        conn.execute(text(ddl))
    conn.commit()
    n1 = conn.execute(text("SELECT COUNT(*) FROM discussions_sociales")).scalar()
    n2 = conn.execute(text("SELECT COUNT(*) FROM knowledge_chunks")).scalar()
    print(f"OK — discussions_sociales: {n1} msgs | knowledge_chunks: {n2} chunks")
