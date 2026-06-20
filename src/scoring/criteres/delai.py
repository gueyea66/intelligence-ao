"""Critère : délai de réponse — score /15."""


def evaluer(ao: dict, config: dict) -> float:
    jours = ao.get("jours_restants")
    if jours is None:
        return 7   # inconnu

    if jours >= 30:    return 15
    elif jours >= 21:  return 12
    elif jours >= 14:  return 9
    elif jours >= 7:   return 5
    elif jours >= 3:   return 2
    else:              return 0   # trop tard
