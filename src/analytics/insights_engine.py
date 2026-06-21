"""
Moteur d'insights statistiques — analyse approfondie des données marché.

Méthodes utilisées :
- Statistiques descriptives (mean, median, percentiles, IQR)
- Détection anomalies prix par z-score (|z| > 2.5 = aberrant)
- Indice de concentration Herfindahl-Hirschman (HHI)
- Régression linéaire simple (tendance prix dans le temps)
- Entropie de Shannon (diversité d'un marché)
"""
import logging
import math
import statistics
from datetime import datetime, timedelta
from collections import Counter

logger = logging.getLogger(__name__)


# ── Statistiques descriptives ─────────────────────────────────────────────────

def stats_prix(prix_list: list[float]) -> dict:
    """Stats complètes sur une liste de prix."""
    if not prix_list:
        return {}
    p = sorted([x for x in prix_list if x and x > 0])
    if not p:
        return {}

    n = len(p)
    mean = sum(p) / n
    median = statistics.median(p)
    std = statistics.stdev(p) if n > 1 else 0

    def percentile(lst, pct):
        idx = int(len(lst) * pct / 100)
        return lst[min(idx, len(lst) - 1)]

    q1 = percentile(p, 25)
    q3 = percentile(p, 75)
    iqr = q3 - q1

    return {
        "n":       n,
        "min":     p[0],
        "max":     p[-1],
        "mean":    round(mean, 0),
        "median":  round(median, 0),
        "std":     round(std, 0),
        "q1":      round(q1, 0),
        "q3":      round(q3, 0),
        "iqr":     round(iqr, 0),
        "cv":      round(std / mean * 100, 1) if mean else 0,  # coefficient variation
    }


def detecter_anomalies_prix(produits: list, seuil_z: float = 2.5) -> list[dict]:
    """Retourne les produits avec un prix anormal (z-score > seuil)."""
    prix = [p.prix_actuel for p in produits if p.prix_actuel and p.prix_actuel > 0]
    if len(prix) < 3:
        return []

    mean = sum(prix) / len(prix)
    std = statistics.stdev(prix)
    if std == 0:
        return []

    anomalies = []
    for p in produits:
        if not p.prix_actuel or p.prix_actuel <= 0:
            continue
        z = abs(p.prix_actuel - mean) / std
        if z > seuil_z:
            anomalies.append({
                "id":         str(p.id),
                "produit":    f"{p.marque or ''} {p.modele or ''}".strip()[:80],
                "prix":       p.prix_actuel,
                "z_score":    round(z, 2),
                "deviation":  "sur-évalué" if p.prix_actuel > mean else "sous-évalué",
                "source":     p.source,
                "categorie":  p.categorie_1,
            })

    return sorted(anomalies, key=lambda x: x["z_score"], reverse=True)[:20]


# ── Indices de marché ─────────────────────────────────────────────────────────

def herfindahl_hirschman(parts_marche: dict) -> dict:
    """
    Indice HHI = somme des carrés des parts de marché.
    HHI < 1500 : marché concurrentiel
    1500-2500 : concentration modérée
    > 2500 : marché concentré (quasi-monopole)
    """
    total = sum(parts_marche.values())
    if total == 0:
        return {"hhi": 0, "interpretation": "données insuffisantes"}

    hhi = sum((v / total * 100) ** 2 for v in parts_marche.values())
    hhi = round(hhi)

    if hhi < 1500:
        interpretation = "Marché concurrentiel"
    elif hhi < 2500:
        interpretation = "Concentration modérée"
    else:
        interpretation = "Marché concentré — risque monopole"

    return {"hhi": hhi, "interpretation": interpretation, "nb_acteurs": len(parts_marche)}


def entropie_shannon(distribution: dict) -> float:
    """
    Entropie de Shannon — mesure la diversité d'un marché.
    H = 0 : monopole total
    H = log2(n) : distribution parfaitement uniforme
    """
    total = sum(distribution.values())
    if total == 0:
        return 0.0
    probs = [v / total for v in distribution.values() if v > 0]
    return round(-sum(p * math.log2(p) for p in probs), 3)


# ── Tendances temporelles ─────────────────────────────────────────────────────

def tendance_prix(prix_dates: list[tuple]) -> dict:
    """
    Régression linéaire simple sur (date, prix).
    prix_dates = [(datetime, float), ...]
    Retourne pente (XOF/jour), direction, R².
    """
    if len(prix_dates) < 3:
        return {"direction": "données insuffisantes"}

    # Convertir dates en jours depuis le premier point
    t0 = min(d for d, _ in prix_dates)
    pts = [(( d - t0).days, p) for d, p in prix_dates if p and p > 0]
    if len(pts) < 3:
        return {"direction": "données insuffisantes"}

    n = len(pts)
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    ss_xx = sum((x - mean_x) ** 2 for x in xs)

    if ss_xx == 0:
        return {"direction": "stable"}

    pente = ss_xy / ss_xx
    intercept = mean_y - pente * mean_x

    # R²
    y_pred = [pente * x + intercept for x in xs]
    ss_res = sum((y - yp) ** 2 for y, yp in zip(ys, y_pred))
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    direction = "hausse" if pente > 5 else ("baisse" if pente < -5 else "stable")

    return {
        "pente_par_jour":   round(pente, 1),
        "direction":        direction,
        "r2":               round(r2, 3),
        "prix_debut":       round(intercept, 0),
        "prix_fin_estime":  round(intercept + pente * max(xs), 0),
    }


# ── Runner principal ──────────────────────────────────────────────────────────

def generer_insights(config: dict, session=None) -> dict:
    """
    Génère l'ensemble des insights pour le dashboard.
    Retourne un dict structuré par thème.
    """
    from src.database.models import get_session, Produit, AppelOffre
    if session is None:
        session = get_session(config)

    # ── Produits par catégorie ────────────────────────────────────────────────
    produits = session.query(Produit).filter(
        Produit.prix_actuel.isnot(None),
        Produit.prix_actuel > 0,
        Produit.prix_actuel < 50_000_000,
    ).limit(3000).all()

    # Stats par catégorie
    par_cat = {}
    for p in produits:
        cat = p.categorie_1 or "Divers"
        par_cat.setdefault(cat, []).append(p.prix_actuel)

    stats_categories = {cat: stats_prix(prix) for cat, prix in par_cat.items()}

    # Top marques par volume
    marques = Counter(p.marque for p in produits if p.marque)
    top_marques = dict(marques.most_common(20))

    # HHI par catégorie (concentration marques)
    hhi_par_cat = {}
    for cat, prods in {c: [p for p in produits if p.categorie_1 == c] for c in par_cat}.items():
        dist_marques = Counter(p.marque for p in prods if p.marque)
        if dist_marques:
            hhi_par_cat[cat] = herfindahl_hirschman(dict(dist_marques))

    # Anomalies prix
    anomalies = detecter_anomalies_prix(produits)

    # Entropie des catégories (diversité globale)
    dist_cats = {c: len(v) for c, v in par_cat.items()}
    entropie_globale = entropie_shannon(dist_cats)

    # Stats AOs
    aos = session.query(AppelOffre).filter(AppelOffre.score.isnot(None)).all()
    scores = [ao.score for ao in aos if ao.score]
    budgets = [ao.budget_estime for ao in aos if ao.budget_estime and ao.budget_estime > 0]

    nb_sources = len({p.source for p in produits if p.source})
    session.close()

    return {
        "timestamp":          datetime.utcnow().isoformat(),
        "nb_produits":        len(produits),
        "nb_sources":         nb_sources,
        "stats_categories":   stats_categories,
        "top_marques":        top_marques,
        "hhi_par_categorie":  hhi_par_cat,
        "anomalies_prix":     anomalies,
        "entropie_marche":    entropie_globale,
        "distribution_cats":  dist_cats,
        "ao_scores":          stats_prix(scores) if scores else {},
        "ao_budgets":         stats_prix(budgets) if budgets else {},
        "nb_anomalies":       len(anomalies),
    }
