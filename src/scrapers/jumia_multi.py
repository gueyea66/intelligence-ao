"""
Jumia Multi-Pays — Côte d'Ivoire, Ghana, Nigeria, Mali
Extension du scraper jumia_sn.py pour couvrir la région Afrique de l'Ouest.
Stocke dans la même table produits avec pays différent.
"""
import re
import time
import hashlib
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Pays → (domaine, devise, top catégories prioritaires)
PAYS_CONFIG = {
    "Côte d'Ivoire": {
        'base_url': 'https://www.jumia.ci',
        'devise': 'XOF',
        'categories': {
            'telephones':     '/telephones-portables/',
            'electronique':   '/electronique/',
            'informatique':   '/ordinateurs-portables/',
            'electromenager': '/electromenager/',
            'alimentation':   '/epicerie-boissons/',
            'mode_homme':     '/mode-homme/',
            'mode_femme':     '/mode-femme/',
        },
    },
    'Ghana': {
        'base_url': 'https://www.jumia.com.gh',
        'devise': 'GHS',  # Cedi ghanéen — converti en XOF côté DB si besoin
        'categories': {
            'telephones':     '/phones-tablets/',
            'electronique':   '/electronics/',
            'informatique':   '/computing/',
            'electromenager': '/home-appliances/',
            'alimentation':   '/grocery/',
        },
    },
    'Nigeria': {
        'base_url': 'https://www.jumia.com.ng',
        'devise': 'NGN',  # Naira nigérian
        'categories': {
            'telephones':     '/phones-tablets/',
            'electronique':   '/electronics/',
            'informatique':   '/computing/',
        },
    },
    'Mali': {
        'base_url': 'https://www.jumia.ml',
        'devise': 'XOF',
        'categories': {
            'telephones':     '/telephones-portables/',
            'electronique':   '/electronique/',
            'informatique':   '/ordinateurs-portables/',
        },
    },
}

MAX_PAGES = 3  # 3 pages par catégorie pour les nouveaux pays (moins agressif)


def parse_price(text: str) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r'[^\d.]', '', text.replace('\xa0', '').replace(' ', '').replace(',', '.'))
    try:
        val = float(cleaned) if cleaned else None
        # Sanity check : entre 100 et 100M (unité locale)
        if val and 100 <= val <= 100_000_000:
            return val
        return None
    except ValueError:
        return None


def scrape_pays(pays: str, config: dict, max_pages: int = MAX_PAGES) -> list[dict]:
    """Scrape toutes les catégories configurées pour un pays."""
    results = []
    base_url = config['base_url']
    devise = config['devise']

    for cat_name, path in config['categories'].items():
        for page in range(1, max_pages + 1):
            url = f"{base_url}{path}?page={page}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                if resp.status_code != 200:
                    logger.warning(f"[{pays}] {url} → HTTP {resp.status_code}")
                    break

                soup = BeautifulSoup(resp.text, 'html.parser')
                articles = soup.select('article.prd, article[data-sku]')
                if not articles:
                    logger.debug(f"[{pays}] {cat_name} page {page} → 0 articles, stop")
                    break

                for art in articles:
                    name_el = art.select_one('.name, h3.name, [data-name]')
                    price_el = art.select_one('.prc, .price, [data-price]')
                    old_el = art.select_one('.old, .old-price, s.prc')
                    brand_el = art.select_one('.brand, [data-brand]')
                    link_el = art.select_one('a[href]')

                    name = name_el.get_text(strip=True) if name_el else None
                    if not name:
                        continue

                    prix = parse_price(price_el.get_text(strip=True) if price_el else None)
                    prix_barre = parse_price(old_el.get_text(strip=True) if old_el else None)
                    marque = brand_el.get_text(strip=True) if brand_el else None
                    url_prod = base_url + link_el['href'] if link_el and link_el.get('href', '').startswith('/') else None

                    uid = hashlib.md5(f"{pays}|{cat_name}|{name}".encode()).hexdigest()

                    results.append({
                        'id': uid,
                        'source': f"jumia_{pays.lower().replace(' ', '_').replace(\"'\", '')}",
                        'date_collecte': datetime.utcnow(),
                        'pays': pays,
                        'categorie_1': cat_name,
                        'categorie_std': cat_name.replace('_', '-'),
                        'description': name,
                        'marque': marque,
                        'prix_actuel': prix,
                        'prix_barre': prix_barre,
                        'promotion': prix_barre is not None and prix_barre > (prix or 0),
                        'devise': devise,
                        'url_source': url_prod,
                        'disponibilite': 'disponible',
                    })

                time.sleep(0.8)  # politesse

            except requests.RequestException as e:
                logger.error(f"[{pays}] {url} → {e}")
                break

        logger.info(f"[{pays}] {cat_name} → {len([r for r in results if r['categorie_1'] == cat_name])} produits")

    return results


def save_to_db(products: list[dict], db_conn) -> int:
    """Insère ou met à jour les produits dans la table produits."""
    saved = 0
    for p in products:
        try:
            db_conn.execute("""
                INSERT INTO produits
                  (id, source, date_collecte, pays, categorie_1, categorie_std,
                   description, marque, prix_actuel, prix_barre, promotion,
                   devise, url_source, disponibilite)
                VALUES
                  (%(id)s, %(source)s, %(date_collecte)s, %(pays)s, %(categorie_1)s, %(categorie_std)s,
                   %(description)s, %(marque)s, %(prix_actuel)s, %(prix_barre)s, %(promotion)s,
                   %(devise)s, %(url_source)s, %(disponibilite)s)
                ON CONFLICT (id) DO UPDATE SET
                  prix_actuel = EXCLUDED.prix_actuel,
                  prix_barre = EXCLUDED.prix_barre,
                  promotion = EXCLUDED.promotion,
                  date_collecte = EXCLUDED.date_collecte
            """, p)
            saved += 1
        except Exception as e:
            logger.warning(f"DB error for {p.get('description', '?')[:40]}: {e}")
    return saved


def run(pays_list: list[str] | None = None, db_conn=None) -> dict[str, int]:
    """
    Point d'entrée principal.
    pays_list = None → scrape tous les pays configurés
    """
    target_pays = pays_list or list(PAYS_CONFIG.keys())
    stats = {}

    for pays in target_pays:
        if pays not in PAYS_CONFIG:
            logger.warning(f"Pays non configuré : {pays}")
            continue

        config = PAYS_CONFIG[pays]
        logger.info(f"Scraping Jumia {pays}...")
        products = scrape_pays(pays, config)
        logger.info(f"  → {len(products)} produits collectés")

        if db_conn and products:
            saved = save_to_db(products, db_conn)
            stats[pays] = saved
        else:
            stats[pays] = len(products)

    return stats


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    results = run()
    for pays, count in results.items():
        print(f"{pays}: {count} produits")
