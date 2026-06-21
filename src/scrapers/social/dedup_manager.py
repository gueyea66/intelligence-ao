"""
Gestionnaire de déduplication pour les scrapers sociaux.
Stratégie : par canal, on mémorise le dernier message_id vu.
Pour les messages sans ID stable, on utilise un hash SHA256 du contenu.
Table: social_scraper_state (état par canal) + index sur message_id.
"""
import hashlib
import json
import os
from datetime import datetime
from typing import Optional
from sqlalchemy import text


def content_hash(texte: str, date: Optional[datetime] = None) -> str:
    """Hash stable pour messages sans ID natif (Facebook)."""
    key = f"{texte[:200]}|{date.date().isoformat() if date else ''}"
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]


class DedupManager:
    """
    Maintient l'état de scraping par (plateforme, canal_id).
    Stocke en DB : dernier message_id, dernier timestamp, nb messages vus.
    """

    STATE_TABLE = """
    CREATE TABLE IF NOT EXISTS social_scraper_state (
        id SERIAL PRIMARY KEY,
        plateforme VARCHAR(50) NOT NULL,
        canal_id VARCHAR(255) NOT NULL,
        canal_nom VARCHAR(255),
        last_message_id VARCHAR(255),
        last_run TIMESTAMP DEFAULT NOW(),
        last_success TIMESTAMP,
        nb_runs INTEGER DEFAULT 0,
        nb_inserted_total INTEGER DEFAULT 0,
        actif BOOLEAN DEFAULT TRUE,
        UNIQUE(plateforme, canal_id)
    )
    """

    def __init__(self, session):
        self.session = session
        self._ensure_tables()

    def _ensure_tables(self):
        try:
            self.session.execute(text(self.STATE_TABLE))
            self.session.commit()
        except Exception:
            self.session.rollback()

    def get_last_message_id(self, plateforme: str, canal_id: str) -> Optional[str]:
        """Retourne le dernier message_id connu pour ce canal."""
        row = self.session.execute(text(
            "SELECT last_message_id FROM social_scraper_state "
            "WHERE plateforme=:p AND canal_id=:c"
        ), {"p": plateforme, "c": canal_id}).fetchone()
        return row[0] if row else None

    def update_state(self, plateforme: str, canal_id: str, canal_nom: str,
                     last_message_id: str, nb_inserted: int):
        """Met à jour l'état après un run réussi."""
        self.session.execute(text("""
            INSERT INTO social_scraper_state
                (plateforme, canal_id, canal_nom, last_message_id, last_run,
                 last_success, nb_runs, nb_inserted_total)
            VALUES (:p, :c, :n, :mid, NOW(), NOW(), 1, :nb)
            ON CONFLICT (plateforme, canal_id) DO UPDATE SET
                canal_nom = EXCLUDED.canal_nom,
                last_message_id = EXCLUDED.last_message_id,
                last_run = NOW(),
                last_success = NOW(),
                nb_runs = social_scraper_state.nb_runs + 1,
                nb_inserted_total = social_scraper_state.nb_inserted_total + EXCLUDED.nb_inserted_total
        """), {
            "p": plateforme, "c": canal_id, "n": canal_nom,
            "mid": last_message_id, "nb": nb_inserted
        })
        self.session.commit()

    def is_duplicate(self, plateforme: str, canal_id: str, message_id: str) -> bool:
        """Vérifie si ce message est déjà en DB."""
        row = self.session.execute(text(
            "SELECT 1 FROM discussions_sociales "
            "WHERE plateforme=:p AND canal_id=:c AND message_id=:mid LIMIT 1"
        ), {"p": plateforme, "c": canal_id, "mid": message_id}).fetchone()
        return row is not None

    def filter_new_messages(self, messages: list[dict]) -> list[dict]:
        """
        Filtre une liste de messages pour ne garder que les nouveaux.
        Pour les threads : compare par message_id unique.
        """
        new_msgs = []
        seen = set()
        for msg in messages:
            key = (msg["plateforme"], msg["canal_id"], msg["message_id"])
            if key in seen:
                continue
            seen.add(key)
            if not self.is_duplicate(*key):
                new_msgs.append(msg)
        return new_msgs

    def get_all_states(self) -> list[dict]:
        """Retourne l'état de tous les canaux (pour monitoring dashboard)."""
        rows = self.session.execute(text("""
            SELECT plateforme, canal_nom, canal_id, last_message_id,
                   last_run, last_success, nb_runs, nb_inserted_total, actif
            FROM social_scraper_state
            ORDER BY last_run DESC
        """)).fetchall()
        return [dict(zip(
            ["plateforme", "canal", "canal_id", "last_message_id",
             "last_run", "last_success", "nb_runs", "nb_inserted", "actif"],
            r
        )) for r in rows]
