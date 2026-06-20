"""Critère : niveau de concurrence — score /10."""

# Sources ONU et BAD ont moins de concurrence locale que DCMP
_CONCURRENCE_SOURCE = {
    "UNGM":          10,   # AO ONU — peu de soumissionnaires locaux
    "BAD":           9,
    "Banque Mondiale": 8,
    "DgMarket":       7,
    "DCMP Sénégal":   5,   # très concurrentiel localement
}

_CONCURRENCE_CAT = {
    "Logistique":     9,
    "Intermédiation": 9,
    "Transport":      8,
    "Fournitures":    6,
    "Informatique":   5,
    "Travaux BTP":    4,
}


def evaluer(ao: dict, config: dict) -> float:
    source = ao.get("source", "")
    cat    = ao.get("categorie", "")

    score_src = _CONCURRENCE_SOURCE.get(source, 6)
    score_cat = _CONCURRENCE_CAT.get(cat, 6)

    return round((score_src + score_cat) / 2, 1)
