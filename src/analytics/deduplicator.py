"""
Déduplication par similarité de chaînes (rapidfuzz) — sans scikit-learn.
Groupe les produits quasi-identiques et supprime les doublons.
"""
import logging
import re
from unidecode import unidecode
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

SEUIL = 0.88  # ratio > 88% = doublon


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _cle(p) -> str:
    txt = unidecode(f"{p.marque or ''} {p.modele or ''}")
    txt = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', txt.lower())).strip()
    prix = str(int(p.prix_actuel or 0))
    return f"{txt}|{prix}"


def run_deduplication(config: dict) -> dict:
    from src.database.models import get_session, Produit

    session = get_session(config)
    sources = [r[0] for r in session.query(Produit.source).distinct().all()]

    total_supprime = 0
    stats = {}

    for source in sources:
        produits = session.query(Produit).filter(Produit.source == source)\
            .order_by(Produit.date_collecte.desc()).all()

        if len(produits) < 2:
            continue

        logger.info(f"Dédup {source}: {len(produits)} produits")
        cles = [_cle(p) for p in produits]
        garder = [True] * len(produits)

        # Comparaison par fenêtre glissante (plus rapide que O(n²) complet)
        for i in range(len(produits)):
            if not garder[i]:
                continue
            for j in range(i + 1, min(i + 200, len(produits))):
                if not garder[j]:
                    continue
                if _ratio(cles[i], cles[j]) >= SEUIL:
                    garder[j] = False

        nb = 0
        for idx, keep in enumerate(garder):
            if not keep:
                session.delete(produits[idx])
                nb += 1

        session.commit()
        total_supprime += nb
        apres = len(produits) - nb
        stats[source] = {"avant": len(produits), "supprimes": nb, "apres": apres}
        logger.info(f"  {source}: {nb} doublons supprimés → {apres} restants")

    session.close()
    return {"total_supprime": total_supprime, "par_source": stats}

def run(config=None):
    result = run_deduplication(config)
    return result.get('total_supprime', 0)
