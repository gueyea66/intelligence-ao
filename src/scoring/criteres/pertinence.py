"""Critère : pertinence sectorielle — score /25."""

_SECTEURS_FORTS = {
    "Informatique":   25,
    "Transport":      22,
    "Fournitures":    20,
    "Énergie":        20,
    "Santé":          18,
    "Travaux BTP":    15,
    "Alimentation":   15,
    "Services":       12,
    "Autre":           8,
}


def evaluer(ao: dict, config: dict) -> float:
    cat = ao.get("categorie", "Autre")
    score = _SECTEURS_FORTS.get(cat, 8)

    # Bonus si pays prioritaire
    pays_prio = config.get("geo", {}).get("pays_prioritaires", [])
    if ao.get("pays") in pays_prio:
        score = min(25, score + 3)

    return score
