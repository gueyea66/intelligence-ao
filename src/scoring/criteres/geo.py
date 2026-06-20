"""Critère : accessibilité géographique — score /15."""


def evaluer(ao: dict, config: dict) -> float:
    pays = ao.get("pays", "")
    pays_prio = config.get("geo", {}).get("pays_prioritaires", [])
    pays_sec  = config.get("geo", {}).get("pays_secondaires", [])

    if pays == "Sénégal":             return 15  # marché local
    elif pays in pays_prio:           return 12  # Afrique de l'Ouest
    elif pays in pays_sec:            return 9
    elif pays in ("Multi-pays", ""):  return 7   # international ouvert
    else:                             return 4   # hors zone
