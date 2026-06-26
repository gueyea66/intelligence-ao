"""
UN Comtrade — Prix d'importation détaillés par code HS6
Source : https://comtradeplus.un.org / API v1
Enrichit donnees_macro avec prix CAF/FOB d'importation par catégorie produit.

Codes HS6 prioritaires pour Afrique de l'Ouest :
  - 8517: Téléphones, smartphones
  - 8471: Ordinateurs
  - 8418: Réfrigérateurs / congélateurs
  - 8415: Climatiseurs
  - 8528: Téléviseurs
  - 1006: Riz
  - 1507-1515: Huiles végétales
  - 1701: Sucre
  - 0402: Lait en poudre
  - 2710: Carburants / huile
"""
import time
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 ComtradeBot/1.0',
    'Accept': 'application/json',
}

# Pays importateurs cibles (codes ISO-3)
PAYS_IMPORTATEURS = {
    'Sénégal': 'SEN',
    "Côte d'Ivoire": 'CIV',
    'Mali': 'MLI',
    'Burkina Faso': 'BFA',
    'Ghana': 'GHA',
    'Nigeria': 'NGA',
}

# HS codes → label court pour donnees_macro
HS_CODES = {
    '851712': ('telephones', 'Téléphones portables (HS 851712)'),
    '847130': ('informatique', 'Ordinateurs portables (HS 847130)'),
    '841810': ('electromenager', 'Réfrigérateurs (HS 841810)'),
    '841510': ('climatisation', 'Climatiseurs (HS 841510)'),
    '852872': ('electronique', 'Téléviseurs (HS 852872)'),
    '100630': ('alimentation', 'Riz semi-blanchi (HS 100630)'),
    '150710': ('alimentation', 'Huile de soja brute (HS 150710)'),
    '170111': ('alimentation', 'Sucre brut (HS 170111)'),
    '040221': ('alimentation', 'Lait en poudre (HS 040221)'),
    '271012': ('materiel-professionnel', 'Diesel (HS 271012)'),
}

COMTRADE_BASE = 'https://comtradeapi.un.org/data/v1/get'


def fetch_comtrade(reporter_iso3: str, hs_code: str, year: int) -> dict | None:
    """
    Appelle l'API Comtrade (mode public sans clé — limité à 500 req/heure).
    Retourne valeur totale importée + quantité → calcul prix unitaire.
    """
    params = {
        'typeCode': 'C',         # Marchandises
        'freqCode': 'A',         # Annuel
        'clCode': 'HS',          # Nomenclature HS
        'period': str(year),
        'reporterCode': reporter_iso3,
        'cmdCode': hs_code,
        'flowCode': 'M',         # Importation
        'partnerCode': '0',      # Monde entier
        'partner2Code': '0',
        'customsCode': 'C00',
        'motCode': '0',
        'maxRecords': 10,
        'format': 'JSON',
        'countOnly': 'false',
    }

    try:
        resp = requests.get(COMTRADE_BASE, params=params, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('data') and len(data['data']) > 0:
                return data['data'][0]
        elif resp.status_code == 429:
            logger.warning("Comtrade rate limit — attente 60s")
            time.sleep(60)
        return None
    except Exception as e:
        logger.warning(f"Comtrade error {reporter_iso3}/{hs_code}: {e}")
        return None


def compute_unit_price_fcfa(row: dict, pays: str) -> float | None:
    """
    Calcule le prix unitaire d'importation en XOF.
    valeur_USD / quantite_kg → prix USD/kg → converti en XOF
    Taux de change approximatif : 1 USD ≈ 600 XOF
    """
    val_usd = row.get('primaryValue') or row.get('cifvalue') or 0
    qty_kg = row.get('netWgt') or row.get('qty') or 0

    if not val_usd or not qty_kg or qty_kg == 0:
        return None

    prix_usd_kg = float(val_usd) / float(qty_kg)
    # Taux approximatif — en production remplacer par taux réel de donnees_macro
    taux_xof_usd = 600.0
    return round(prix_usd_kg * taux_xof_usd, 2)


def scrape_all(years: list[int] | None = None) -> list[dict]:
    if years is None:
        years = [2021, 2022, 2023, 2024]

    records = []

    for pays_nom, iso3 in PAYS_IMPORTATEURS.items():
        for hs_code, (cat_std, label) in HS_CODES.items():
            for year in years:
                logger.info(f"Comtrade {pays_nom} / {label} / {year}")
                row = fetch_comtrade(iso3, hs_code, year)

                if row:
                    val_usd = row.get('primaryValue') or row.get('cifvalue')
                    qty_kg = row.get('netWgt') or row.get('qty')
                    prix_fcfa_kg = compute_unit_price_fcfa(row, pays_nom)

                    if val_usd:
                        records.append({
                            'source': 'Comtrade_HS6',
                            'pays': pays_nom,
                            'indicateur': f'Import {label}',
                            'annee': year,
                            'valeur': round(float(val_usd) / 1_000_000, 4),  # en millions USD
                            'unite': 'M USD',
                            'date_collecte': datetime.utcnow(),
                            'notes': f'HS {hs_code} | categorie: {cat_std} | qty: {qty_kg} kg',
                        })

                    if prix_fcfa_kg:
                        records.append({
                            'source': 'Comtrade_HS6',
                            'pays': pays_nom,
                            'indicateur': f'Prix import {label} (XOF/kg)',
                            'annee': year,
                            'valeur': prix_fcfa_kg,
                            'unite': 'XOF/kg',
                            'date_collecte': datetime.utcnow(),
                            'notes': f'HS {hs_code} | categorie: {cat_std}',
                        })

                time.sleep(1.2)  # Respecter rate limit Comtrade (500/h ≈ 1.2s/req)

    logger.info(f"Comtrade total: {len(records)} records")
    return records


def save_to_db(records: list[dict], db_conn) -> int:
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
                  date_collecte = EXCLUDED.date_collecte,
                  notes = EXCLUDED.notes
            """, r)
            saved += 1
        except Exception as e:
            logger.warning(f"DB error: {e}")
    return saved


def run(db_conn=None, years: list[int] | None = None) -> dict:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    records = scrape_all(years)
    if db_conn:
        saved = save_to_db(records, db_conn)
        return {'collected': len(records), 'saved': saved}
    return {'collected': len(records), 'saved': 0}


if __name__ == '__main__':
    result = run()
    print(f"Collecté: {result['collected']} | Sauvé: {result['saved']}")
