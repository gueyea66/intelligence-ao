"""
Détecteur de patterns temporels pour les discussions sociales.

Patterns détectés :
1. Émergence de tendance  — topic/keyword apparaît soudainement
2. Déclin de tendance     — topic/keyword disparaît progressivement
3. Spike de sentiment     — variation brusque sentiment positif/négatif
4. Spike de prix          — prix d'un produit monte/descend soudainement
5. Heure de poste         — distribution horaire pour optimiser les runs
6. Récurrence hebdomadaire — certains sujets reviennent à jours fixes
"""
import math
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import text


# ─── Utilitaires statistiques ────────────────────────────────────────────────

def moving_average(values: list[float], window: int = 3) -> list[float]:
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start:i + 1]
        result.append(sum(chunk) / len(chunk))
    return result


def detect_changepoint(series: list[float], threshold: float = 1.5) -> list[int]:
    """
    Détecte les points de rupture dans une série temporelle.
    Retourne les indices où un changement significatif se produit.
    """
    if len(series) < 4:
        return []
    ma = moving_average(series, 3)
    mean = sum(ma) / len(ma)
    std = math.sqrt(sum((x - mean) ** 2 for x in ma) / len(ma)) or 1

    changepoints = []
    for i in range(1, len(ma)):
        delta = abs(ma[i] - ma[i - 1])
        if delta > threshold * std:
            changepoints.append(i)
    return changepoints


def z_score_series(values: list[float]) -> list[float]:
    if not values:
        return []
    mean = sum(values) / len(values)
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) or 1
    return [(v - mean) / std for v in values]


# ─── Analyse des heures de poste optimales ────────────────────────────────────

def analyze_posting_hours(session) -> dict:
    """
    Analyse les heures et jours de poste pour optimiser les crons.
    Retourne les 2 heures UTC optimales pour les runs quotidiens.
    """
    rows = session.execute(text("""
        SELECT
            EXTRACT(HOUR FROM date_publication) as heure,
            COUNT(*) as nb
        FROM discussions_sociales
        WHERE date_publication IS NOT NULL
          AND date_publication > NOW() - INTERVAL '30 days'
        GROUP BY heure
        ORDER BY heure
    """)).fetchall()

    if not rows:
        # Valeurs par défaut basées sur les habitudes AO
        return {
            "run1_utc": 6,   # 6h UTC = 6h Dakar, pic matin
            "run2_utc": 18,  # 18h UTC = 18h Dakar, pic soir
            "cron1": "0 6 * * *",
            "cron2": "0 18 * * *",
            "distribution": {},
            "source": "default",
        }

    hours = {int(r[0]): int(r[1]) for r in rows}
    total = sum(hours.values())

    # Trouver les 2 pics principaux (en ignorant les voisins dans ±2h)
    peaks = sorted(hours.items(), key=lambda x: -x[1])
    selected = []
    for h, nb in peaks:
        if not any(abs(h - s[0]) <= 2 for s in selected):
            selected.append((h, nb))
        if len(selected) == 2:
            break

    # Trier par heure pour avoir run1 < run2
    selected.sort(key=lambda x: x[0])

    # Décaler d'1h en avance pour capturer le début du pic
    run1 = max(0, selected[0][0] - 1) if selected else 6
    run2 = max(0, selected[1][0] - 1) if len(selected) > 1 else 18

    return {
        "run1_utc": run1,
        "run2_utc": run2,
        "cron1": f"0 {run1} * * *",
        "cron2": f"0 {run2} * * *",
        "distribution": {str(h): nb for h, nb in sorted(hours.items())},
        "top_hours": [(h, nb, round(100 * nb / total, 1)) for h, nb in sorted(peaks[:5], key=lambda x: x[0])],
        "source": "data",
    }


# ─── Détection de tendances émergentes ───────────────────────────────────────

def detect_emerging_topics(session, window_days: int = 7) -> list[dict]:
    """
    Détecte les topics qui émergent (fréquence récente > fréquence historique × seuil).
    """
    rows = session.execute(text("""
        WITH recent AS (
            SELECT topic, COUNT(*) as nb_recent
            FROM discussions_sociales,
                LATERAL jsonb_array_elements_text(COALESCE(topics, '[]')) AS topic
            WHERE date_publication > NOW() - INTERVAL '7 days'
            GROUP BY topic
        ),
        historical AS (
            SELECT topic, COUNT(*) as nb_hist
            FROM discussions_sociales,
                LATERAL jsonb_array_elements_text(COALESCE(topics, '[]')) AS topic
            WHERE date_publication BETWEEN NOW() - INTERVAL '30 days' AND NOW() - INTERVAL '7 days'
            GROUP BY topic
        )
        SELECT r.topic, r.nb_recent, COALESCE(h.nb_hist, 0) as nb_hist,
            CASE WHEN COALESCE(h.nb_hist, 0) = 0 THEN 999
                 ELSE r.nb_recent::float / h.nb_hist END as ratio
        FROM recent r
        LEFT JOIN historical h ON r.topic = h.topic
        ORDER BY ratio DESC
    """)).fetchall()

    return [
        {
            "topic": r[0],
            "nb_recent": r[1],
            "nb_historique": r[2],
            "ratio_croissance": round(float(r[3]), 2),
            "statut": "nouveau" if r[2] == 0 else "en_hausse" if r[3] > 2 else "stable",
        }
        for r in rows
    ]


def detect_declining_topics(session) -> list[dict]:
    """Topics qui diminuent dans les 7 derniers jours vs les 7 jours précédents."""
    rows = session.execute(text("""
        WITH recent AS (
            SELECT topic, COUNT(*) as nb_recent
            FROM discussions_sociales,
                LATERAL jsonb_array_elements_text(COALESCE(topics, '[]')) AS topic
            WHERE date_publication > NOW() - INTERVAL '7 days'
            GROUP BY topic
        ),
        previous AS (
            SELECT topic, COUNT(*) as nb_prev
            FROM discussions_sociales,
                LATERAL jsonb_array_elements_text(COALESCE(topics, '[]')) AS topic
            WHERE date_publication BETWEEN NOW() - INTERVAL '14 days' AND NOW() - INTERVAL '7 days'
            GROUP BY topic
        )
        SELECT p.topic, COALESCE(r.nb_recent, 0) as nb_recent, p.nb_prev,
            COALESCE(r.nb_recent, 0)::float / p.nb_prev as ratio
        FROM previous p
        LEFT JOIN recent r ON p.topic = r.topic
        WHERE COALESCE(r.nb_recent, 0)::float / p.nb_prev < 0.5
          AND p.nb_prev >= 5
        ORDER BY ratio ASC
    """)).fetchall()

    return [
        {
            "topic": r[0],
            "nb_recent": r[1],
            "nb_precedent": r[2],
            "ratio_declin": round(float(r[3]), 2),
        }
        for r in rows
    ]


# ─── Patterns de prix ─────────────────────────────────────────────────────────

def detect_price_spikes(session) -> list[dict]:
    """
    Détecte les spikes de prix mentionnés dans les discussions.
    Compare la moyenne des 3 derniers jours vs moyenne des 7-14 jours.
    """
    rows = session.execute(text("""
        WITH recent_prices AS (
            SELECT
                (prix_item->>'montant')::float as montant,
                date_publication::date as jour
            FROM discussions_sociales,
                LATERAL jsonb_array_elements(COALESCE(prix_mentionnes, '[]')) AS prix_item
            WHERE contient_prix = TRUE
              AND (prix_item->>'montant')::float BETWEEN 1000 AND 10000000
              AND date_publication > NOW() - INTERVAL '14 days'
        ),
        by_period AS (
            SELECT
                CASE WHEN jour > NOW() - INTERVAL '3 days' THEN 'recent' ELSE 'previous' END as periode,
                AVG(montant) as prix_moyen,
                COUNT(*) as nb
            FROM recent_prices
            GROUP BY periode
        )
        SELECT * FROM by_period
    """)).fetchall()

    periods = {r[0]: {"prix_moyen": float(r[1]), "nb": int(r[2])} for r in rows}
    recent = periods.get("recent", {})
    previous = periods.get("previous", {})

    if not recent or not previous or previous["prix_moyen"] == 0:
        return []

    variation = (recent["prix_moyen"] - previous["prix_moyen"]) / previous["prix_moyen"]

    result = []
    if abs(variation) > 0.15:  # >15% de variation
        result.append({
            "type": "spike_prix_global",
            "variation_pct": round(variation * 100, 1),
            "prix_recent": round(recent["prix_moyen"]),
            "prix_precedent": round(previous["prix_moyen"]),
            "nb_mentions": recent["nb"],
            "direction": "hausse" if variation > 0 else "baisse",
        })
    return result


# ─── Patterns de sentiment ────────────────────────────────────────────────────

def detect_sentiment_shifts(session) -> list[dict]:
    """Détecte les bascules de sentiment (canal/plateforme qui devient soudainement négatif)."""
    rows = session.execute(text("""
        WITH daily AS (
            SELECT
                canal,
                date_publication::date as jour,
                AVG(score_sentiment) as sentiment_moyen,
                COUNT(*) as nb
            FROM discussions_sociales
            WHERE date_publication > NOW() - INTERVAL '14 days'
              AND sentiment IS NOT NULL
            GROUP BY canal, jour
            HAVING COUNT(*) >= 3
        )
        SELECT canal,
            AVG(CASE WHEN jour > NOW() - INTERVAL '3 days' THEN sentiment_moyen END) as s_recent,
            AVG(CASE WHEN jour <= NOW() - INTERVAL '3 days' THEN sentiment_moyen END) as s_previous
        FROM daily
        GROUP BY canal
        HAVING COUNT(*) >= 4
    """)).fetchall()

    shifts = []
    for r in rows:
        canal, s_recent, s_prev = r[0], r[1], r[2]
        if s_recent is None or s_prev is None:
            continue
        delta = float(s_recent) - float(s_prev)
        if abs(delta) > 0.3:
            shifts.append({
                "canal": canal,
                "sentiment_recent": round(float(s_recent), 3),
                "sentiment_precedent": round(float(s_prev), 3),
                "delta": round(delta, 3),
                "direction": "degradation" if delta < 0 else "amelioration",
            })

    return sorted(shifts, key=lambda x: abs(x["delta"]), reverse=True)


# ─── Récurrences hebdomadaires ────────────────────────────────────────────────

def detect_weekly_patterns(session) -> list[dict]:
    """Topics qui apparaissent à jours fixes de la semaine."""
    rows = session.execute(text("""
        SELECT
            topic,
            EXTRACT(DOW FROM date_publication) as dow,
            COUNT(*) as nb
        FROM discussions_sociales,
            LATERAL jsonb_array_elements_text(COALESCE(topics, '[]')) AS topic
        WHERE date_publication > NOW() - INTERVAL '60 days'
        GROUP BY topic, dow
        HAVING COUNT(*) >= 3
        ORDER BY topic, nb DESC
    """)).fetchall()

    topic_days = defaultdict(lambda: defaultdict(int))
    for r in rows:
        topic_days[r[0]][int(r[1])] += int(r[2])

    JOURS = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]
    patterns = []
    for topic, days in topic_days.items():
        total = sum(days.values())
        dominant_day = max(days, key=days.get)
        dominant_pct = days[dominant_day] / total * 100
        if dominant_pct >= 35:  # >35% concentré sur 1 jour
            patterns.append({
                "topic": topic,
                "jour_dominant": JOURS[dominant_day],
                "concentration_pct": round(dominant_pct, 1),
                "distribution": {JOURS[d]: nb for d, nb in days.items()},
            })

    return sorted(patterns, key=lambda x: -x["concentration_pct"])


# ─── Rapport complet de patterns ─────────────────────────────────────────────

def full_pattern_report(session) -> dict:
    """Rapport consolidé de tous les patterns détectés."""
    return {
        "posting_hours": analyze_posting_hours(session),
        "emerging_topics": detect_emerging_topics(session),
        "declining_topics": detect_declining_topics(session),
        "price_spikes": detect_price_spikes(session),
        "sentiment_shifts": detect_sentiment_shifts(session),
        "weekly_patterns": detect_weekly_patterns(session),
        "generated_at": datetime.utcnow().isoformat(),
    }
