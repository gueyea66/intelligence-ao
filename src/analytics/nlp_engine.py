"""
Moteur NLP pour analyser les discussions sociales de l'économie informelle.
Techniques : TF-IDF, sentiment lexical, détection de prix, NER léger, topics.
Pas de modèles lourds — fonctionne sans GPU, déployable sur GitHub Actions.
"""
import re
import math
import hashlib
from collections import Counter
from typing import Optional


# ─── Détection de langue ────────────────────────────────────────────────────

WOLOF_MARKERS = {"waaw", "deedeet", "ak", "bi", "gi", "yi", "bu", "fi",
                 "xam", "def", "dem", "jox", "nit", "yow", "man", "noo"}
ARABIC_PATTERN = re.compile(r'[؀-ۿ]')


def detect_language(text: str) -> str:
    words = set(text.lower().split())
    if ARABIC_PATTERN.search(text):
        return "ar"
    wolof_count = len(words & WOLOF_MARKERS)
    if wolof_count >= 2:
        return "wo"
    # Heuristique fr/en : mots outil fréquents
    fr_words = {"est", "les", "des", "pour", "dans", "sur", "pas", "avec", "qui", "que"}
    en_words = {"the", "is", "are", "for", "this", "that", "and", "with", "have"}
    fr_score = len(words & fr_words)
    en_score = len(words & en_words)
    if fr_score >= en_score:
        return "fr"
    return "en"


# ─── Extraction de prix ──────────────────────────────────────────────────────

PRICE_PATTERNS = [
    # 50 000 FCFA / 50k fcfa / 50.000 CFA
    re.compile(r'(\d[\d\s\.,]+)\s*(fcfa|cfa|xof|f\.?cfa)', re.IGNORECASE),
    # 50 000 F
    re.compile(r'(\d[\d\s]+)\s*f(?:\b)', re.IGNORECASE),
    # 50$ / 50 dollars
    re.compile(r'(\d[\d\s\.,]+)\s*(\$|dollars?|usd)', re.IGNORECASE),
    # Prix : 5000
    re.compile(r'prix\s*:?\s*(\d[\d\s\.,]+)', re.IGNORECASE),
    # à 5000 ou pour 5000
    re.compile(r'(?:a|pour|vendu|vend|cede)\s+(\d[\d\s\.,]+)\s*(fcfa|cfa|f\b)?', re.IGNORECASE),
]


def extract_prices(text: str) -> list[dict]:
    results = []
    for pat in PRICE_PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(1).replace(' ', '').replace('.', '').replace(',', '')
            try:
                montant = int(raw)
                if 100 <= montant <= 100_000_000:  # filtre aberrations
                    devise = "FCFA"
                    if "$" in m.group(0) or "dollar" in m.group(0).lower():
                        devise = "USD"
                    results.append({"montant": montant, "devise": devise, "contexte": m.group(0)[:40]})
            except (ValueError, IndexError):
                pass
    return results


# ─── Détection de contact ────────────────────────────────────────────────────

CONTACT_PATTERN = re.compile(
    r'(?:\+?221|00221)?\s*(?:7[0-9])\s*\d{3}\s*\d{2}\s*\d{2}|'
    r'@\w{3,}|'
    r't\.me/\w+|'
    r'wa\.me/\d+',
    re.IGNORECASE
)


def contains_contact(text: str) -> bool:
    return bool(CONTACT_PATTERN.search(text))


# ─── Analyse de sentiment (lexique) ─────────────────────────────────────────

POS_WORDS = {
    "bon", "bien", "excellent", "super", "parfait", "qualite", "solide",
    "fiable", "rapide", "disponible", "livraison", "professionnel",
    "recommande", "satisfait", "content", "propre", "nouveau", "original",
    "garanti", "certifie", "top", "best", "nice", "good", "great"
}

NEG_WORDS = {
    "arnaque", "escroquerie", "faux", "voleur", "menteur", "defaut",
    "casse", "probleme", "mauvais", "nul", "cher", "trop cher", "escroc",
    "degat", "defectueux", "lent", "retard", "absent", "manque",
    "rupture", "indisponible", "refus", "decevant", "mauvaise qualite",
    "fake", "bad", "scam", "fraud", "broken", "slow"
}

NEGATORS = {"pas", "non", "jamais", "aucun", "sans", "ni", "ne"}


def analyze_sentiment(text: str) -> tuple[str, float]:
    """Retourne (label, score) — score entre -1 et +1."""
    import unicodedata
    def norm(s):
        s = s.lower()
        s = unicodedata.normalize('NFD', s)
        return ''.join(c for c in s if unicodedata.category(c) != 'Mn')

    words = norm(text).split()
    score = 0.0
    for i, w in enumerate(words):
        negated = i > 0 and words[i-1] in NEGATORS
        if w in POS_WORDS:
            score += -0.5 if negated else 1.0
        elif w in NEG_WORDS:
            score += 0.5 if negated else -1.0

    # Normaliser
    n = max(len(words), 1)
    normalized = max(-1.0, min(1.0, score / math.sqrt(n)))

    if normalized > 0.1:
        label = "positif"
    elif normalized < -0.1:
        label = "negatif"
    else:
        label = "neutre"

    return label, round(normalized, 3)


# ─── Détection de pain points ────────────────────────────────────────────────

PAIN_PATTERNS = [
    re.compile(r"(j['']ai perdu\s.{5,50})", re.IGNORECASE),
    re.compile(r"(impossible de\s.{5,50})", re.IGNORECASE),
    re.compile(r"(on nous\s.{5,50})", re.IGNORECASE),
    re.compile(r"(le probleme\s.{0,10}est\s.{5,50})", re.IGNORECASE),
    re.compile(r"(difficile de\s.{5,50})", re.IGNORECASE),
    re.compile(r"(arnaque[^\.]{0,60})", re.IGNORECASE),
    re.compile(r"(escroquer.{0,60})", re.IGNORECASE),
    re.compile(r"(qualit[eé] [a-z ]{0,20}mauvais.{0,40})", re.IGNORECASE),
    re.compile(r"(trop cher.{0,40})", re.IGNORECASE),
    re.compile(r"(rupture de stock.{0,40})", re.IGNORECASE),
    re.compile(r"(livraison.{0,20}(?:lente|retard|jamais arrivé).{0,30})", re.IGNORECASE),
]


def detect_pain_points(text: str) -> list[str]:
    found = []
    for pat in PAIN_PATTERNS:
        for m in pat.finditer(text):
            snippet = m.group(1).strip()[:120]
            if snippet not in found:
                found.append(snippet)
    return found


# ─── Classification du type de message ───────────────────────────────────────

TYPE_KEYWORDS = {
    "annonce": ["vend", "vente", "cede", "a vendre", "disponible", "stock", "livraison"],
    "question": ["quelqu'un", "est-ce que", "comment", "ou trouver", "besoin de", "cherche"],
    "plainte": ["arnaque", "escro", "probleme", "jamais recu", "faux", "defectueux"],
    "info": ["prix actuel", "taux", "marche", "tendance", "nouveau", "arrivage"],
    "discussion": [],  # défaut si rien ne match
}


def classify_type(text: str) -> str:
    text_lower = text.lower()
    scores = {t: 0 for t in TYPE_KEYWORDS}
    for type_label, kws in TYPE_KEYWORDS.items():
        for kw in kws:
            if kw in text_lower:
                scores[type_label] += 1
    best = max(scores.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "discussion"


# ─── Topics / thèmes ────────────────────────────────────────────────────────

TOPIC_KEYWORDS = {
    "commerce": ["vente", "achat", "boutique", "marche", "commerce", "grossiste", "importation"],
    "prix": ["prix", "tarif", "cout", "fcfa", "cfa", "reduction", "promotion", "rabais"],
    "transport": ["livraison", "transport", "dakar", "thiès", "kaolack", "transit", "douane"],
    "electronique": ["telephone", "samsung", "iphone", "laptop", "tablette", "chargeur"],
    "alimentaire": ["riz", "huile", "sucre", "farine", "mil", "mais", "arachide"],
    "textile": ["tissu", "wax", "bazin", "broderie", "couture", "vetement", "pagne"],
    "immobilier": ["maison", "appartement", "terrain", "loyer", "bail", "vente terrain"],
    "finance": ["credit", "pret", "remboursement", "tontine", "epargne", "transfert"],
    "sante": ["medicament", "pharmacie", "sante", "hopital", "clinique", "traitement"],
    "emploi": ["travail", "emploi", "cherche emploi", "recrutement", "stagiaire"],
}


def detect_topics(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for topic, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            if kw in text_lower:
                found.append(topic)
                break
    return found or ["general"]


# ─── TF-IDF simple ──────────────────────────────────────────────────────────

STOP_WORDS_FR = {
    "le", "la", "les", "de", "du", "des", "et", "en", "un", "une",
    "pour", "dans", "sur", "avec", "par", "ou", "qui", "que", "se",
    "ce", "au", "aux", "il", "elle", "ils", "elles", "je", "tu",
    "nous", "vous", "mais", "donc", "car", "si", "ne", "pas", "plus",
    "est", "sont", "a", "y", "n", "c", "d", "l", "j", "m", "s"
}


def compute_tfidf_keywords(texts: list[str], top_n: int = 20) -> list[tuple[str, float]]:
    """Retourne les top_n termes les plus distinctifs sur un corpus de messages."""
    import unicodedata

    def tokenize(text):
        text = text.lower()
        text = unicodedata.normalize('NFD', text)
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = [w for w in text.split() if len(w) > 2 and w not in STOP_WORDS_FR]
        return tokens

    docs = [tokenize(t) for t in texts]
    N = len(docs)
    if N == 0:
        return []

    # IDF
    df = Counter()
    for doc in docs:
        for w in set(doc):
            df[w] += 1

    # TF global
    tf_global = Counter()
    for doc in docs:
        for w in doc:
            tf_global[w] += 1

    # Score TF-IDF
    scores = {}
    for w, tf in tf_global.items():
        idf = math.log((N + 1) / (df[w] + 1)) + 1
        scores[w] = tf * idf

    return sorted(scores.items(), key=lambda x: -x[1])[:top_n]


# ─── Pipeline complet sur un message ────────────────────────────────────────

def analyze_message(texte: str) -> dict:
    """Analyse complète d'un message. Retourne un dict prêt pour insertion DB."""
    import hashlib

    langue = detect_language(texte)
    sentiment_label, sentiment_score = analyze_sentiment(texte)
    prix = extract_prices(texte)
    pain_points = detect_pain_points(texte)
    topics = detect_topics(texte)
    type_msg = classify_type(texte)

    return {
        "langue": langue,
        "sentiment": sentiment_label,
        "score_sentiment": sentiment_score,
        "prix_mentionnes": prix,
        "pain_points": pain_points,
        "topics": topics,
        "type_message": type_msg,
        "contient_prix": len(prix) > 0,
        "contient_contact": contains_contact(texte),
    }
