"""
Export CSV, JSON et Excel depuis les données de la base.
Format et dossier configurables dans config.yaml.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _prepare_dossier(config: dict) -> str:
    dossier = config["export"]["dossier_sortie"]
    Path(dossier).mkdir(parents=True, exist_ok=True)
    return dossier


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _orm_to_dict(obj) -> dict[str, Any]:
    """Convertit un objet SQLAlchemy en dict."""
    d = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        d[col.name] = val
    return d


# ── Appels d'offres ───────────────────────────────────────────────────────────

def export_aos(aos: list, config: dict, format_: str | None = None) -> str:
    fmt = format_ or config["export"]["format_defaut"]
    dossier = _prepare_dossier(config)
    filename = f"appels_offres_{_timestamp()}"

    rows = [_orm_to_dict(ao) for ao in aos]
    df = pd.DataFrame(rows)

    path = _write(df, dossier, filename, fmt)
    logger.info(f"Export AOs: {path} ({len(rows)} lignes)")
    return path


# ── Produits ──────────────────────────────────────────────────────────────────

def export_produits(produits: list, config: dict, format_: str | None = None) -> str:
    fmt = format_ or config["export"]["format_defaut"]
    dossier = _prepare_dossier(config)
    filename = f"produits_{_timestamp()}"

    rows = [_orm_to_dict(p) for p in produits]
    df = pd.DataFrame(rows)

    path = _write(df, dossier, filename, fmt)
    logger.info(f"Export produits: {path} ({len(rows)} lignes)")
    return path


# ── Informel ──────────────────────────────────────────────────────────────────

def export_informel(annonces: list, config: dict, format_: str | None = None) -> str:
    fmt = format_ or config["export"]["format_defaut"]
    dossier = _prepare_dossier(config)
    filename = f"informel_{_timestamp()}"

    rows = [_orm_to_dict(a) for a in annonces]
    df = pd.DataFrame(rows)

    path = _write(df, dossier, filename, fmt)
    logger.info(f"Export informel: {path} ({len(rows)} lignes)")
    return path


# ── Export unifié multi-onglets Excel ────────────────────────────────────────

def export_rapport_complet(config: dict, session) -> str:
    """Génère un Excel multi-onglets : AOs prioritaires, Produits, Informel."""
    from src.database.models import AppelOffre, Produit, AnnoncInformel

    dossier  = _prepare_dossier(config)
    filename = f"rapport_complet_{_timestamp()}.xlsx"
    path     = os.path.join(dossier, filename)

    aos      = session.query(AppelOffre).order_by(AppelOffre.score.desc().nullslast()).limit(500).all()
    produits = session.query(Produit).order_by(Produit.date_collecte.desc()).limit(1000).all()
    informel = session.query(AnnoncInformel).order_by(AnnoncInformel.date_collecte.desc()).limit(500).all()

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _df(aos).to_excel(writer, sheet_name="Appels d'Offres", index=False)
        _df(produits).to_excel(writer, sheet_name="Catalogue Produits", index=False)
        _df(informel).to_excel(writer, sheet_name="Marché Informel", index=False)

    logger.info(f"Rapport complet: {path}")
    return path


# ── Helpers ──────────────────────────────────────────────────────────────────

def _df(objects: list) -> pd.DataFrame:
    if not objects:
        return pd.DataFrame()
    return pd.DataFrame([_orm_to_dict(o) for o in objects])


def _write(df: pd.DataFrame, dossier: str, filename: str, fmt: str) -> str:
    fmt = fmt.lower()
    if fmt == "excel":
        path = os.path.join(dossier, f"{filename}.xlsx")
        df.to_excel(path, index=False, engine="openpyxl")
    elif fmt == "csv":
        path = os.path.join(dossier, f"{filename}.csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
    elif fmt == "json":
        path = os.path.join(dossier, f"{filename}.json")
        df.to_json(path, orient="records", force_ascii=False, indent=2)
    else:
        raise ValueError(f"Format inconnu: {fmt}")
    return path
