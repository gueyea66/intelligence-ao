"""
Opérations CRUD communes et helpers de requêtage.
"""
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from src.database.models import AppelOffre, AnnoncInformel, Produit, get_session, init_db


def setup(config: dict) -> None:
    """Initialise la base (crée les tables si besoin)."""
    init_db(config)


# ── Produits ──────────────────────────────────────────────────────────────────

def upsert_produit(session: Session, data: dict) -> bool:
    """Insert un produit. Retourne True si nouvel enregistrement."""
    produit = Produit(**{k: v for k, v in data.items() if hasattr(Produit, k)})
    session.add(produit)
    session.flush()
    return True


def get_produits(config: dict, filters: dict | None = None) -> list[Produit]:
    session = get_session(config)
    q = session.query(Produit)
    if filters:
        if filters.get("source"):
            q = q.filter(Produit.source == filters["source"])
        if filters.get("categorie"):
            q = q.filter(Produit.categorie_1 == filters["categorie"])
        if filters.get("marque"):
            q = q.filter(Produit.marque == filters["marque"])
        if filters.get("pays"):
            q = q.filter(Produit.pays == filters["pays"])
        if filters.get("depuis_jours"):
            since = datetime.utcnow() - timedelta(days=filters["depuis_jours"])
            q = q.filter(Produit.date_collecte >= since)
    return q.order_by(Produit.date_collecte.desc()).all()


# ── Appels d'offres ───────────────────────────────────────────────────────────

def upsert_ao(session: Session, data: dict) -> bool:
    """Insert ou met à jour un AO (clé = référence)."""
    ref = data.get("reference")
    if ref:
        existing = session.query(AppelOffre).filter_by(reference=ref).first()
        if existing:
            for k, v in data.items():
                if hasattr(existing, k) and v is not None:
                    setattr(existing, k, v)
            return False  # update
    ao = AppelOffre(**{k: v for k, v in data.items() if hasattr(AppelOffre, k)})
    session.add(ao)
    return True  # insert


def get_aos(config: dict, filters: dict | None = None) -> list[AppelOffre]:
    session = get_session(config)
    q = session.query(AppelOffre)
    if filters:
        if filters.get("statut"):
            q = q.filter(AppelOffre.statut == filters["statut"])
        if filters.get("pays"):
            q = q.filter(AppelOffre.pays == filters["pays"])
        if filters.get("score_min") is not None:
            q = q.filter(AppelOffre.score >= filters["score_min"])
        if filters.get("actifs_seulement"):
            q = q.filter(AppelOffre.date_limite >= datetime.utcnow())
    return q.order_by(AppelOffre.score.desc().nullslast()).all()


# ── Informel ──────────────────────────────────────────────────────────────────

def upsert_informel(session: Session, data: dict) -> bool:
    item = AnnoncInformel(**{k: v for k, v in data.items() if hasattr(AnnoncInformel, k)})
    session.add(item)
    session.flush()
    return True


def get_informel(config: dict, filters: dict | None = None) -> list[AnnoncInformel]:
    session = get_session(config)
    q = session.query(AnnoncInformel)
    if filters:
        if filters.get("zone"):
            q = q.filter(AnnoncInformel.vendeur_zone == filters["zone"])
        if filters.get("produit"):
            q = q.filter(AnnoncInformel.produit.ilike(f"%{filters['produit']}%"))
        if filters.get("type"):
            q = q.filter(AnnoncInformel.type == filters["type"])
    return q.order_by(AnnoncInformel.date_collecte.desc()).all()


# ── Stats rapides pour le dashboard ──────────────────────────────────────────

def stats_summary(config: dict) -> dict[str, Any]:
    session = get_session(config)
    return {
        "nb_produits":   session.query(Produit).count(),
        "nb_aos":        session.query(AppelOffre).count(),
        "nb_aos_actifs": session.query(AppelOffre).filter(
            AppelOffre.date_limite >= datetime.utcnow()
        ).count(),
        "nb_informel":   session.query(AnnoncInformel).count(),
        "ao_prioritaires": session.query(AppelOffre).filter(
            AppelOffre.score >= 70
        ).count(),
    }
