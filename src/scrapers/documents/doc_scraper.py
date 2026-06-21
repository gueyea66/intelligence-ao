"""
Scraper de documents institutionnels : UN, Banque Mondiale, ANSD, BCEAO, etc.
Télécharge, extrait le texte des PDF, crée des résumés structurés.
Stocké en table: documents_institutionnels
"""
import os
import re
import hashlib
import logging
import requests
from datetime import datetime
from typing import Optional
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ─── Sources documentaires ────────────────────────────────────────────────────

DOCUMENT_SOURCES = {
    # Banque Mondiale — Afrique de l'Ouest
    "world_bank": [
        {
            "url": "https://api.worldbank.org/v2/country/SN/indicator/NY.GDP.MKTP.CD?format=json&mrv=5",
            "type": "api_json",
            "titre": "PIB Sénégal — Banque Mondiale",
            "pays": "Sénégal",
            "categorie": "macro",
        },
        {
            "url": "https://api.worldbank.org/v2/country/CI/indicator/FP.CPI.TOTL.ZG?format=json&mrv=5",
            "type": "api_json",
            "titre": "Inflation Côte d'Ivoire — Banque Mondiale",
            "pays": "Côte d'Ivoire",
            "categorie": "macro",
        },
        {
            "url": "https://api.worldbank.org/v2/country/ML/indicator/NY.GDP.MKTP.KD.ZG?format=json&mrv=5",
            "type": "api_json",
            "titre": "Croissance PIB Mali — Banque Mondiale",
            "pays": "Mali",
            "categorie": "macro",
        },
    ],
    # ANSD — Agence Nationale de la Statistique et de la Démographie (Sénégal)
    "ansd": [
        {
            "url": "https://www.ansd.sn/ressources/publications/indices/IPC/Note_IPC.pdf",
            "type": "pdf",
            "titre": "Note IPC mensuelle — ANSD Sénégal",
            "pays": "Sénégal",
            "categorie": "prix_consommation",
        },
        {
            "url": "https://www.ansd.sn/ressources/publications/rapports/RapportEconomique.pdf",
            "type": "pdf",
            "titre": "Rapport Économique Social — ANSD",
            "pays": "Sénégal",
            "categorie": "economie",
        },
    ],
    # BCEAO — Banque Centrale États Afrique de l'Ouest
    "bceao": [
        {
            "url": "https://www.bceao.int/sites/default/files/2024-01/Bulletin_Statistique_mensuel.pdf",
            "type": "pdf",
            "titre": "Bulletin Statistique BCEAO",
            "pays": "UEMOA",
            "categorie": "monetaire",
        },
        {
            "url": "https://www.bceao.int/sites/default/files/note_information_economique.pdf",
            "type": "pdf",
            "titre": "Note d'Information Économique BCEAO",
            "pays": "UEMOA",
            "categorie": "monetaire",
        },
    ],
    # UN Comtrade — commerce international
    "un_comtrade": [
        {
            "url": "https://comtradeapi.un.org/data/v1/get/C/A/2023/SN/all/all?fmt=json",
            "type": "api_json",
            "titre": "Flux commerciaux Sénégal 2023 — UN Comtrade",
            "pays": "Sénégal",
            "categorie": "commerce_international",
            "headers": {"Ocp-Apim-Subscription-Key": os.environ.get("UN_COMTRADE_API_KEY", "")},
        },
    ],
    # INS — Côte d'Ivoire
    "ins_ci": [
        {
            "url": "https://www.ins.ci/n/publications/Bulletin_mensuel_de_statistique.pdf",
            "type": "pdf",
            "titre": "Bulletin Mensuel de Statistique — INS Côte d'Ivoire",
            "pays": "Côte d'Ivoire",
            "categorie": "statistiques",
        },
    ],
    # INSTAT — Mali
    "instat_mali": [
        {
            "url": "https://instat-mali.org/contenu/pub/ipc_mali_note.pdf",
            "type": "pdf",
            "titre": "Note IPC — INSTAT Mali",
            "pays": "Mali",
            "categorie": "prix_consommation",
        },
    ],
}

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS documents_institutionnels (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50),
    url TEXT,
    url_hash VARCHAR(64) UNIQUE,
    titre TEXT,
    pays VARCHAR(100),
    categorie VARCHAR(100),
    date_publication TIMESTAMP,
    date_collecte TIMESTAMP DEFAULT NOW(),
    type_document VARCHAR(20),
    texte_extrait TEXT,
    donnees_json JSONB,
    resume TEXT,
    indicateurs_cles JSONB,
    nb_pages INTEGER,
    taille_octets INTEGER,
    est_nouveau BOOLEAN DEFAULT TRUE
)
"""


# ─── Extraction de texte PDF ──────────────────────────────────────────────────

def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 50000) -> tuple[str, int]:
    """Extrait le texte d'un PDF. Retourne (texte, nb_pages)."""
    try:
        import pdfplumber
        import io
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages[:30]:  # max 30 pages
                text = page.extract_text() or ""
                pages.append(text)
            full_text = "\n\n".join(pages)
            return full_text[:max_chars], len(pdf.pages)
    except ImportError:
        pass

    # Fallback: PyMuPDF
    try:
        import fitz
        import io
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        texts = []
        for page in doc:
            texts.append(page.get_text())
        return "\n\n".join(texts)[:max_chars], doc.page_count
    except ImportError:
        pass

    return "[PDF extraction indisponible — installer pdfplumber ou PyMuPDF]", 0


# ─── Extraction d'indicateurs clés depuis le texte ───────────────────────────

INDICATOR_PATTERNS = [
    (r'(?:taux d[\'']inflation|inflation)\s*[:\s]+([+-]?\d+[,.]?\d*)\s*%', 'inflation_pct'),
    (r'(?:taux de croissance|croissance du PIB)\s*[:\s]+([+-]?\d+[,.]?\d*)\s*%', 'pib_croissance_pct'),
    (r'(?:IPC|indice des prix)\s*[:\s]+(\d+[,.]?\d*)', 'ipc'),
    (r'(?:taux de change|1 EUR?)\s*[:\s=]+(\d+[,.]?\d*)\s*(?:FCFA|CFA|XOF)', 'taux_change_eur_fcfa'),
    (r'(?:taux directeur|taux d[\'']intérêt)\s*[:\s]+(\d+[,.]?\d*)\s*%', 'taux_directeur_pct'),
    (r'(?:taux de chômage|chômage)\s*[:\s]+(\d+[,.]?\d*)\s*%', 'chomage_pct'),
    (r'balance commerciale\s*[:\s]+([+-]?\d[\d\s]*)\s*(milliards?|millions?)?', 'balance_commerciale'),
]


def extract_indicators(text: str) -> dict:
    indicators = {}
    for pattern, key in INDICATOR_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(',', '.').replace(' ', ''))
                indicators[key] = val
            except ValueError:
                pass
    return indicators


# ─── Résumé automatique (sans LLM) ────────────────────────────────────────────

def auto_summarize(text: str, max_sentences: int = 5) -> str:
    """Extrait les phrases les plus informatives (TF-IDF like)."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30][:50]

    key_words = {
        'inflation', 'croissance', 'pib', 'ipc', 'taux', 'milliards', 'millions',
        'fcfa', 'exportation', 'importation', 'déficit', 'excédent', 'emploi',
        'chômage', 'hausse', 'baisse', 'augmentation', 'diminution', 'rapport',
    }

    def sentence_score(s):
        words = s.lower().split()
        return sum(1 for w in words if w in key_words) / (len(words) ** 0.5 + 1)

    scored = sorted(enumerate(sentences), key=lambda x: -sentence_score(x[1]))
    top = sorted(scored[:max_sentences], key=lambda x: x[0])
    return ' '.join(s for _, s in top)


# ─── Collecte et stockage ─────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; IntelligenceAO/1.0; research)",
    "Accept": "application/pdf,application/json,text/html",
}


def scrape_and_store_documents(session):
    """Scrape toutes les sources documentaires et stocke en DB."""
    try:
        session.execute(text(TABLE_SQL))
        session.commit()
    except Exception:
        session.rollback()

    total_inserted = 0
    total_updated = 0

    for source_name, docs in DOCUMENT_SOURCES.items():
        for doc_config in docs:
            url = doc_config["url"]
            url_hash = hashlib.sha256(url.encode()).hexdigest()[:32]

            # Vérifier si déjà en DB (dédup par URL + comparaison taille)
            existing = session.execute(text(
                "SELECT taille_octets FROM documents_institutionnels WHERE url_hash=:h"
            ), {"h": url_hash}).fetchone()

            try:
                hdrs = {**HEADERS, **doc_config.get("headers", {})}
                resp = requests.get(url, headers=hdrs, timeout=30)
                if resp.status_code != 200:
                    logger.warning(f"HTTP {resp.status_code} pour {url}")
                    continue

                content_size = len(resp.content)

                # Si taille identique → pas de nouveau contenu
                if existing and existing[0] == content_size:
                    logger.debug(f"Inchangé: {doc_config['titre']}")
                    continue

                # Extraire contenu selon type
                texte = ""
                donnees_json = None
                nb_pages = 0

                if doc_config["type"] == "pdf":
                    texte, nb_pages = extract_pdf_text(resp.content)
                elif doc_config["type"] == "api_json":
                    donnees_json = resp.json()
                    # Convertir en texte lisible
                    texte = str(donnees_json)[:5000]

                indicators = extract_indicators(texte)
                resume = auto_summarize(texte)

                record_data = {
                    "source": source_name,
                    "url": url,
                    "url_hash": url_hash,
                    "titre": doc_config["titre"],
                    "pays": doc_config["pays"],
                    "categorie": doc_config["categorie"],
                    "date_collecte": datetime.utcnow(),
                    "type_document": doc_config["type"],
                    "texte_extrait": texte[:50000],
                    "donnees_json": str(donnees_json) if donnees_json else None,
                    "resume": resume,
                    "indicateurs_cles": str(indicators) if indicators else None,
                    "nb_pages": nb_pages,
                    "taille_octets": content_size,
                    "est_nouveau": existing is None,
                }

                if existing:
                    session.execute(text("""
                        UPDATE documents_institutionnels SET
                            date_collecte=:date_collecte, texte_extrait=:texte_extrait,
                            donnees_json=:donnees_json, resume=:resume,
                            indicateurs_cles=:indicateurs_cles, taille_octets=:taille_octets,
                            nb_pages=:nb_pages, est_nouveau=FALSE
                        WHERE url_hash=:url_hash
                    """), record_data)
                    total_updated += 1
                else:
                    session.execute(text("""
                        INSERT INTO documents_institutionnels
                            (source, url, url_hash, titre, pays, categorie, date_collecte,
                             type_document, texte_extrait, donnees_json, resume,
                             indicateurs_cles, nb_pages, taille_octets, est_nouveau)
                        VALUES (:source, :url, :url_hash, :titre, :pays, :categorie,
                                :date_collecte, :type_document, :texte_extrait, :donnees_json,
                                :resume, :indicateurs_cles, :nb_pages, :taille_octets, :est_nouveau)
                    """), record_data)
                    total_inserted += 1

                session.commit()
                logger.info(f"{'Nouveau' if not existing else 'Mis à jour'}: {doc_config['titre']}")

            except Exception as e:
                session.rollback()
                logger.warning(f"Erreur {url}: {e}")

    logger.info(f"Documents: {total_inserted} insérés, {total_updated} mis à jour")
    return total_inserted, total_updated
