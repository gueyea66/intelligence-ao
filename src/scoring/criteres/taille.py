"""Critère : taille du marché — score /20."""


def evaluer(ao: dict, config: dict) -> float:
    budget = ao.get("budget_estime") or 0
    devise = ao.get("devise", "XOF")

    # Normaliser en XOF (1 USD ≈ 600 XOF)
    if devise == "USD":
        budget_xof = budget * 600
    elif devise == "EUR":
        budget_xof = budget * 655
    else:
        budget_xof = budget

    if budget_xof >= 500_000_000:      return 20
    elif budget_xof >= 100_000_000:    return 17
    elif budget_xof >= 50_000_000:     return 14
    elif budget_xof >= 10_000_000:     return 10
    elif budget_xof > 0:               return 6
    else:                              return 5   # budget non renseigné
