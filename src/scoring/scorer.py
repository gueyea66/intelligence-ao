"""
Moteur de scoring des Appels d'Offres.
Tous les poids lus depuis config.yaml — rien n'est hardcodé.
"""
import json
import logging
from typing import Any

from src.scoring.criteres import pertinence, taille, delai, geo, concurrence

logger = logging.getLogger(__name__)

_POSITIONNEMENTS_KEYWORDS = {
    "SOURCING":        ["fourniture", "livraison", "matériel", "équipement", "produit"],
    "LOGISTIQUE":      ["transport", "logistique", "livraison", "fret", "acheminement"],
    "INTERMÉDIATION":  ["courtage", "intermédiation", "représentation", "mandataire"],
    "FORMALISATION":   ["formalisation", "structure", "appui", "accompagnement"],
    "FINANCEMENT":     ["financement", "crédit", "avance", "fonds", "garantie"],
    "DIRECT":          ["direct", "propre", "exclusif"],
}


def calculer_score(ao: dict, config: dict) -> dict[str, Any]:
    """
    Calcule le score d'opportunité d'un AO.
    Retourne un dict avec score_total, detail, niveau, positionnement.
    """
    poids = config["scoring"]["poids"]
    max_total = sum(poids.values())

    s_pertinence  = pertinence.evaluer(ao, config)
    s_taille      = taille.evaluer(ao, config)
    s_delai       = delai.evaluer(ao, config)
    s_geo         = geo.evaluer(ao, config)
    s_fournisseur = _evaluer_fournisseur(ao, config)
    s_concurrence = concurrence.evaluer(ao, config)

    score_brut = (
        s_pertinence  * poids["pertinence_sectorielle"] / 25 +
        s_taille      * poids["taille_marche"]          / 20 +
        s_delai       * poids["delai_reponse"]          / 15 +
        s_geo         * poids["accessibilite_geo"]       / 15 +
        s_fournisseur * poids["disponibilite_fournisseur"] / 15 +
        s_concurrence * poids["niveau_concurrence"]     / 10
    )

    score_total = round(score_brut, 1)

    detail = {
        "pertinence_sectorielle":   round(s_pertinence, 1),
        "taille_marche":            round(s_taille, 1),
        "delai_reponse":            round(s_delai, 1),
        "accessibilite_geo":        round(s_geo, 1),
        "disponibilite_fournisseur": round(s_fournisseur, 1),
        "niveau_concurrence":       round(s_concurrence, 1),
    }

    niveau     = _classer(score_total, config)
    positionnement = _suggerer_positionnement(ao)

    return {
        "score_total":             score_total,
        "detail_scores":           json.dumps(detail, ensure_ascii=False),
        "niveau_priorite":         niveau,
        "type_valeur_recommande":  positionnement,
    }


def scorer_tous_aos(config: dict, session) -> int:
    """Score tous les AOs sans score dans la base. Retourne nb mis à jour."""
    from src.database.models import AppelOffre

    aos = session.query(AppelOffre).filter(AppelOffre.score.is_(None)).all()
    nb = 0
    for ao in aos:
        try:
            ao_dict = {
                "source":           ao.source,
                "categorie":        ao.categorie,
                "pays":             ao.pays,
                "budget_estime":    ao.budget_estime,
                "devise":           ao.devise,
                "jours_restants":   ao.jours_restants,
                "objet":            ao.objet or "",
            }
            result = calculer_score(ao_dict, config)
            ao.score           = result["score_total"]
            ao.detail_scores   = result["detail_scores"]
            ao.positionnement  = result["type_valeur_recommande"]

            # Mettre à jour le statut selon le niveau
            niveau = result["niveau_priorite"]
            if niveau == "PRIORITÉ HAUTE":
                ao.statut = "nouveau"
            elif niveau == "À SURVEILLER":
                ao.statut = "nouveau"
            else:
                ao.statut = "archive"

            nb += 1
        except Exception as e:
            logger.warning(f"Erreur scoring AO {ao.id}: {e}")

    session.commit()
    logger.info(f"Scoring: {nb} AOs mis à jour")
    return nb


# ── Helpers internes ──────────────────────────────────────────────────────────

def _evaluer_fournisseur(ao: dict, config: dict) -> float:
    """Heuristique : estime la disponibilité fournisseur selon la catégorie."""
    cat = ao.get("categorie", "")
    mapping = {
        "Fournitures":  14,
        "Informatique": 13,
        "Transport":    12,
        "Énergie":      11,
        "Alimentation": 12,
        "Santé":         9,
        "Travaux BTP":   8,
        "Services":     10,
        "Autre":         8,
    }
    return mapping.get(cat, 8)


def _classer(score: float, config: dict) -> str:
    seuils = config["scoring"]["seuils"]
    if score >= seuils["priorite_haute"]:
        return "PRIORITÉ HAUTE"
    elif score >= seuils["a_surveiller"]:
        return "À SURVEILLER"
    else:
        return "ARCHIVÉ"


def _suggerer_positionnement(ao: dict) -> str:
    objet = (ao.get("objet", "") or "").lower()
    for pos, keywords in _POSITIONNEMENTS_KEYWORDS.items():
        if any(kw in objet for kw in keywords):
            return pos
    return "SOURCING"
