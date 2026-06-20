"""
World Bank Open Data API — indicateurs macro Afrique de l'Ouest.
API gratuite, pas d'auth requise.
Doc : https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
"""
import logging
from datetime import datetime

import requests

from src.database.models import DonneeMacro, get_session
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)

_PAYS_CODES = {
    "Sénégal":       "SN",
    "Côte d'Ivoire": "CI",
    "Mali":          "ML",
    "Burkina Faso":  "BF",
    "Guinée":        "GN",
    "Togo":          "TG",
    "Bénin":         "BJ",
    "Niger":         "NE",
    "Ghana":         "GH",
    "Nigeria":       "NG",
}

# Indicateurs WDI pertinents pour intelligence commerciale
_INDICATEURS = {
    # PIB & Croissance
    "NY.GDP.MKTP.CD":    ("PIB nominal (USD courants)", "PIB", "USD"),
    "NY.GDP.MKTP.KD.ZG": ("Croissance PIB (%)", "PIB", "%"),
    "NY.GDP.PCAP.CD":    ("PIB par habitant (USD)", "PIB", "USD"),
    # Inflation
    "FP.CPI.TOTL.ZG":    ("Inflation CPI (%)", "Inflation", "%"),
    "NY.GDP.DEFL.KD.ZG": ("Déflateur PIB (%)", "Inflation", "%"),
    # Commerce
    "NE.EXP.GNFS.ZS":    ("Exportations % PIB", "Commerce", "%"),
    "NE.IMP.GNFS.ZS":    ("Importations % PIB", "Commerce", "%"),
    "BX.KLT.DINV.WD.GD.ZS": ("IDE entrants % PIB", "Commerce", "%"),
    # Population & Emploi
    "SP.POP.TOTL":       ("Population totale", "Démographie", "personnes"),
    "SP.URB.TOTL.IN.ZS": ("Population urbaine %", "Démographie", "%"),
    "SL.UEM.TOTL.ZS":    ("Chômage % force travail", "Emploi", "%"),
    # Infrastructure
    "IT.NET.USER.ZS":    ("Utilisateurs Internet %", "Infrastructure", "%"),
    "EG.ELC.ACCS.ZS":    ("Accès électricité %", "Infrastructure", "%"),
    # Finance
    "FS.AST.CGOV.GD.ZS": ("Crédit secteur privé % PIB", "Finance", "%"),
}

_API_BASE = "https://api.worldbank.org/v2"


def run(config: dict | None = None) -> int:
    if config is None:
        config = load_config()

    session = get_session(config)
    # Créer les tables si manquantes
    from src.database.models import get_engine, Base
    Base.metadata.create_all(get_engine(config))

    nb_ok = 0
    annee_fin = datetime.now().year - 1
    annee_debut = annee_fin - 9  # 10 ans d'historique

    pays_prioritaires = config["geo"]["pays_prioritaires"]

    for pays_nom in pays_prioritaires:
        code = _PAYS_CODES.get(pays_nom)
        if not code:
            continue

        for wdi_code, (libelle, categorie, unite) in _INDICATEURS.items():
            try:
                url = f"{_API_BASE}/country/{code}/indicator/{wdi_code}"
                params = {
                    "format":     "json",
                    "date":       f"{annee_debut}:{annee_fin}",
                    "per_page":   50,
                }
                resp = requests.get(url, params=params,
                                    timeout=config["scraping"]["timeout"],
                                    headers={"User-Agent": config["scraping"]["user_agent"]})

                if resp.status_code != 200:
                    logger.debug(f"WB {pays_nom} {wdi_code}: HTTP {resp.status_code}")
                    continue

                data = resp.json()
                if len(data) < 2 or not data[1]:
                    continue

                for rec in data[1]:
                    val = rec.get("value")
                    if val is None:
                        continue

                    dm = DonneeMacro(
                        source        = "World Bank",
                        date_collecte = datetime.utcnow(),
                        pays          = pays_nom,
                        indicateur    = libelle,
                        code_wdi      = wdi_code,
                        annee         = int(rec.get("date", 0)),
                        valeur        = float(val),
                        unite         = unite,
                        categorie     = categorie,
                        url_source    = url,
                    )
                    session.add(dm)
                    nb_ok += 1

                session.commit()
                logger.info(f"WB {pays_nom} — {libelle}: OK")

            except Exception as e:
                logger.warning(f"WB {pays_nom} {wdi_code}: {e}")

    session.close()
    logger.info(f"World Bank terminé — {nb_ok} indicateurs collectés")
    return nb_ok
