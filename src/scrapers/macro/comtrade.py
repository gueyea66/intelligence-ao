"""
Intégration UN Comtrade — flux import/export Afrique de l'Ouest.
API publique v3 : https://comtradeplus.un.org/TradeFlow
Retourne les données dans la table produits (macro).
"""
import logging
from datetime import datetime
from typing import Generator

import requests

from src.database.models import Produit, get_session
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)

_SOURCE_NOM = "UN Comtrade"

# Codes ISO3 Afrique de l'Ouest
_COUNTRY_CODES = {
    "Sénégal":       "SEN",
    "Côte d'Ivoire": "CIV",
    "Mali":          "MLI",
    "Burkina Faso":  "BFA",
    "Guinée":        "GIN",
    "Togo":          "TGO",
    "Bénin":         "BEN",
    "Niger":         "NER",
    "Ghana":         "GHA",
    "Nigeria":       "NGA",
}

# Top HS codes pertinents pour l'opérateur
_HS_CODES = [
    "84",   # Machines et appareils mécaniques
    "85",   # Machines électriques
    "87",   # Véhicules automobiles
    "39",   # Matières plastiques
    "73",   # Ouvrages en fonte, fer ou acier
    "10",   # Céréales
    "27",   # Combustibles minéraux
]

_API_BASE = "https://comtradeplus.un.org/TradeFlow"


def run(config: dict | None = None) -> int:
    if config is None:
        config = load_config()

    session = get_session(config)
    nb_ok   = 0
    annee   = datetime.now().year - 1  # données de l'année précédente

    pays_cfg = config["geo"]["pays_prioritaires"]

    for pays_nom in pays_cfg:
        code = _COUNTRY_CODES.get(pays_nom)
        if not code:
            continue

        for hs in _HS_CODES[:3]:  # limiter pour MVP
            try:
                params = {
                    "reporterCode": code,
                    "period":       annee,
                    "productCode":  hs,
                    "tradeFlowCode": "M",   # Imports
                    "typeCode":     "C",
                    "freqCode":     "A",
                    "fmt":          "json",
                    "max":          100,
                }
                headers = {"User-Agent": config["scraping"]["user_agent"]}
                resp = requests.get(_API_BASE, params=params, headers=headers,
                                    timeout=config["scraping"]["timeout"])

                if resp.status_code == 200:
                    data = resp.json()
                    records = data.get("data", [])
                    logger.info(f"Comtrade {pays_nom} HS{hs}: {len(records)} enregistrements")

                    for rec in records:
                        try:
                            val_usd = rec.get("primaryValue", 0) or 0
                            p = Produit(
                                source=_SOURCE_NOM,
                                date_collecte=datetime.utcnow(),
                                categorie_1="Macro",
                                categorie_2=f"HS{hs}",
                                marque="",
                                modele=rec.get("cmdDesc", f"HS {hs}")[:200],
                                description=f"Import {pays_nom} — {rec.get('cmdDesc', '')}",
                                prix_actuel=val_usd,
                                devise="USD",
                                pays=pays_nom,
                                url_source=f"https://comtradeplus.un.org",
                                disponibilite="Données macro",
                            )
                            session.add(p)
                            nb_ok += 1
                        except Exception as e:
                            logger.debug(f"Comtrade record: {e}")

                    session.commit()

                elif resp.status_code == 429:
                    logger.warning("Comtrade rate limit — attente")
                    import time; time.sleep(60)
                else:
                    logger.warning(f"Comtrade {pays_nom} HS{hs}: HTTP {resp.status_code}")

            except Exception as e:
                logger.error(f"Comtrade {pays_nom}: {e}")

    session.close()
    logger.info(f"Comtrade terminé — {nb_ok} enregistrements")
    return nb_ok
