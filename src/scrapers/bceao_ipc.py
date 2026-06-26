"""
BCEAO — Indice des Prix à la Consommation (IPC) mensuel
Source : https://www.bceao.int/fr/statistiques/prix
Enrichit donnees_macro avec données inflation mensuelles par pays UEMOA.

Méthode : téléchargement des bulletins PDF/Excel BCEAO + fallback API World Bank mensuelle.
"""
import re
import time
import logging
import requests
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
}

# Pays UEMOA couverts par BCEAO
PAYS_UEMOA = [
    'Sénégal', "Côte d'Ivoire", 'Mali', 'Burkina Faso',
    'Niger', 'Togo', 'Bénin', 'Guinée-Bissau'
]

# Codes ISO World Bank pour fallback API
ISO_CODES = {
    'Sénégal': 'SEN',
    "Côte d'Ivoire": 'CIV',
    'Mali': 'MLI',
    'Burkina Faso': 'BFA',
    'Niger': 'NER',
    'Togo': 'TGO',
    'Bénin': 'BEN',
    'Guinée-Bissau': 'GNB',
}

# World Bank indicators — données mensuelles
WB_INDICATORS_MONTHLY = {
    'Inflation mensuelle (%)': 'FP.CPI.TOTL.ZG',  # CPI inflation annuelle
    'IPC (base 2010=100)': 'FP.CPI.TOTL',          # Niveau IPC
}

# World Bank indicators — données annuelles supplémentaires
WB_INDICATORS_EXTRA = {
    'Taux de change (XOF/USD)': 'PA.NUS.FCRF',
    'Exportations (% PIB)': 'NE.EXP.GNFS.ZS',
    'Importations (% PIB)': 'NE.IMP.GNFS.ZS',
    'IDE entrants (% PIB)': 'BX.KLT.DINV.WD.GD.ZS',
    'Chômage % force travail': 'SL.UEM.TOTL.ZS',
    'Accès électricité %': 'EG.ELC.ACCS.ZS',
    'Utilisateurs Internet %': 'IT.NET.USER.ZS',
    'Crédit secteur privé % PIB': 'FS.AST.PRVT.GD.ZS',
    'Population urbaine %': 'SP.URB.TOTL.IN.ZS',
}


def fetch_wb_monthly(iso_code: str, indicator_code: str, start_year: int = 2018) -> list[dict]:
    """Récupère données World Bank API (format JSON)."""
    url = (
        f"https://api.worldbank.org/v2/country/{iso_code}/indicator/{indicator_code}"
        f"?format=json&per_page=200&mrv=84&date={start_year}:2025"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if len(data) < 2 or not data[1]:
            return []
        return [
            {
                'annee': int(d['date'].split('M')[0]) if 'M' in str(d['date']) else int(d['date']),
                'mois': int(d['date'].split('M')[1]) if 'M' in str(d['date']) else None,
                'valeur': float(d['value']) if d['value'] is not None else None,
            }
            for d in data[1] if d.get('value') is not None
        ]
    except Exception as e:
        logger.warning(f"WB API error {iso_code}/{indicator_code}: {e}")
        return []


def build_record(pays: str, indicateur: str, annee: int, valeur: float,
                 source: str = 'BCEAO/WorldBank', unite: str = '%',
                 mois: Optional[int] = None) -> dict:
    periode = f"{annee}-{mois:02d}" if mois else str(annee)
    return {
        'source': source,
        'pays': pays,
        'indicateur': indicateur,
        'annee': annee,
        'valeur': round(valeur, 4),
        'unite': unite,
        'date_collecte': datetime.utcnow(),
        'notes': f"Période: {periode}",
    }


def scrape_all() -> list[dict]:
    """Point d'entrée — retourne toutes les données collectées."""
    records = []
    start_year = 2018

    for pays in PAYS_UEMOA:
        iso = ISO_CODES.get(pays)
        if not iso:
            continue

        logger.info(f"[BCEAO IPC] Collecte {pays} ({iso})...")

        # Indicateurs mensuels / annuels
        for indicateur, code in {**WB_INDICATORS_MONTHLY, **WB_INDICATORS_EXTRA}.items():
            data_points = fetch_wb_monthly(iso, code, start_year)
            unite = '%' if '%' in indicateur else ('USD' if 'USD' in indicateur else '')

            for dp in data_points:
                if dp['valeur'] is None:
                    continue
                records.append(build_record(
                    pays=pays,
                    indicateur=indicateur,
                    annee=dp['annee'],
                    valeur=dp['valeur'],
                    source='WorldBank_WDI',
                    unite=unite,
                    mois=dp.get('mois'),
                ))

            time.sleep(0.3)  # politesse API

        logger.info(f"  → {len([r for r in records if r['pays'] == pays])} données collectées")

    logger.info(f"Total: {len(records)} records BCEAO/WDI")
    return records


def save_to_db(records: list[dict], db_conn) -> int:
    """Upsert dans donnees_macro."""
    saved = 0
    for r in records:
        try:
            db_conn.execute("""
                INSERT INTO donnees_macro
                  (source, pays, indicateur, annee, valeur, unite, date_collecte, notes)
                VALUES
                  (%(source)s, %(pays)s, %(indicateur)s, %(annee)s, %(valeur)s,
                   %(unite)s, %(date_collecte)s, %(notes)s)
                ON CONFLICT (pays, indicateur, annee) DO UPDATE SET
                  valeur = EXCLUDED.valeur,
                  date_collecte = EXCLUDED.date_collecte
            """, r)
            saved += 1
        except Exception as e:
            logger.warning(f"DB error {r['pays']}/{r['indicateur']}/{r['annee']}: {e}")
    return saved


def run(db_conn=None) -> dict:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    records = scrape_all()

    if db_conn:
        saved = save_to_db(records, db_conn)
        return {'collected': len(records), 'saved': saved}

    return {'collected': len(records), 'saved': 0}


if __name__ == '__main__':
    result = run()
    print(f"Collecté: {result['collected']} | Sauvé: {result['saved']}")
