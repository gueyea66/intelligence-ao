"""
Pipeline LLM Knowledge — construit une base de connaissance terrain
à partir de discussions_sociales pour enrichir les réponses IA.

Fonctions :
  build_knowledge_base()  → produit des fiches structurées par thème/zone
  get_market_context()    → retourne contexte terrain pour un produit/sujet
  compute_corpus_tfidf()  → identifie les termes clés du moment
  get_price_intelligence()→ résumé prix terrain par catégorie

Stockage : table knowledge_chunks en Supabase (créée auto).
Compatible RAG : chaque chunk = contexte + metadata JSON.
"""

import json
import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text as sql_text

from src.analytics.nlp_engine import compute_tfidf_keywords, detect_topics

logger = logging.getLogger(__name__)

# ── Schema knowledge_chunks ───────────────────────────────────────────────────
CREATE_KNOWLEDGE_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id           SERIAL PRIMARY KEY,
    chunk_type   VARCHAR(50)  NOT NULL,
    sujet        VARCHAR(200) NOT NULL,
    zone         VARCHAR(100) DEFAULT 'Dakar',
    periode      VARCHAR(50),
    contenu      TEXT         NOT NULL,
    metadata     JSONB        DEFAULT '{}',
    sources_count INT         DEFAULT 0,
    confidence   FLOAT        DEFAULT 0.5,
    created_at   TIMESTAMP    DEFAULT NOW(),
    updated_at   TIMESTAMP    DEFAULT NOW(),
    UNIQUE(chunk_type, sujet, zone, periode)
);
"""


def ensure_table(session) -> None:
    try:
        session.execute(sql_text(CREATE_KNOWLEDGE_TABLE))
        session.commit()
    except Exception as e:
        session.rollback()
        logger.warning(f"knowledge_chunks table: {e}")


# ── Extraction depuis discussions_sociales ────────────────────────────────────

def _fetch_recent_discussions(session, days: int = 30, limit: int = 5000) -> list[dict]:
    since = datetime.utcnow() - timedelta(days=days)
    result = session.execute(sql_text("""
        SELECT texte_brut, topics, prix_mentionnes, sentiment,
               pain_points, canal, date_publication
        FROM discussions_sociales
        WHERE date_publication >= :since
          AND texte_brut IS NOT NULL
          AND LENGTH(texte_brut) > 10
        ORDER BY date_publication DESC
        LIMIT :lim
    """), {"since": since, "lim": limit})
    rows = []
    for r in result:
        rows.append({
            "text":   r[0],
            "topics": json.loads(r[1]) if isinstance(r[1], str) else (r[1] or []),
            "prix":   json.loads(r[2]) if isinstance(r[2], str) else (r[2] or []),
            "sentiment": r[3],
            "pain_points": json.loads(r[4]) if isinstance(r[4], str) else (r[4] or []),
            "canal":  r[5],
            "date":   r[6],
        })
    return rows


# ── Chunk 1 — Prix terrain par catégorie ─────────────────────────────────────

def _build_price_chunks(messages: list[dict]) -> list[dict]:
    """Résumé statistique des prix mentionnés par topic."""
    topic_prices: defaultdict[str, list] = defaultdict(list)
    topic_contexts: defaultdict[str, list] = defaultdict(list)

    for m in messages:
        if not m["prix"]:
            continue
        topics = m["topics"] or ["general"]
        for topic in topics:
            for p in m["prix"]:
                montant = p if isinstance(p, (int, float)) else p.get("montant", 0)
                if 100 <= montant <= 100_000_000:
                    topic_prices[topic].append(montant)
                    if len(topic_contexts[topic]) < 5:
                        topic_contexts[topic].append(m["text"][:200])

    chunks = []
    for topic, prices in topic_prices.items():
        if len(prices) < 3:
            continue
        prices_sorted = sorted(prices)
        n = len(prices_sorted)
        mean = sum(prices_sorted) / n
        median = prices_sorted[n // 2]
        p25 = prices_sorted[n // 4]
        p75 = prices_sorted[3 * n // 4]
        std = math.sqrt(sum((p - mean) ** 2 for p in prices_sorted) / n)

        contenu = (
            f"PRIX TERRAIN — {topic.upper()} (Afrique de l'Ouest, marché informel)\n"
            f"Basé sur {n} mentions récentes dans les discussions de terrain.\n\n"
            f"Prix médian : {median:,.0f} FCFA\n"
            f"Prix moyen  : {mean:,.0f} FCFA\n"
            f"Fourchette  : {p25:,.0f} – {p75:,.0f} FCFA (Q1–Q3)\n"
            f"Dispersion  : ±{std:,.0f} FCFA (écart-type)\n\n"
            f"Exemples de messages sources :\n"
            + "\n".join(f"• {c}" for c in topic_contexts[topic][:3])
        )

        chunks.append({
            "chunk_type": "prix_terrain",
            "sujet": topic,
            "zone": "Afrique de l'Ouest",
            "periode": datetime.utcnow().strftime("%Y-%m"),
            "contenu": contenu,
            "metadata": json.dumps({
                "n": n, "mean": round(mean), "median": round(median),
                "p25": round(p25), "p75": round(p75), "std": round(std),
            }),
            "sources_count": n,
            "confidence": min(0.9, 0.5 + n / 200),
        })

    return chunks


# ── Chunk 2 — Signaux terrain (pain points agrégés) ───────────────────────────

def _build_pain_point_chunks(messages: list[dict]) -> list[dict]:
    topic_pains: defaultdict[str, Counter] = defaultdict(Counter)

    for m in messages:
        for pp in (m["pain_points"] or []):
            for topic in (m["topics"] or ["general"]):
                topic_pains[topic][pp] += 1

    chunks = []
    for topic, pain_counter in topic_pains.items():
        if not pain_counter:
            continue
        top_pains = pain_counter.most_common(10)
        contenu = (
            f"SIGNAUX D'ALERTE — {topic.upper()} (marché informel terrain)\n"
            f"Problèmes les plus mentionnés dans les discussions :\n\n"
            + "\n".join(f"• ({cnt}x) {pain}" for pain, cnt in top_pains)
        )
        chunks.append({
            "chunk_type": "pain_points",
            "sujet": topic,
            "zone": "Afrique de l'Ouest",
            "periode": datetime.utcnow().strftime("%Y-%m"),
            "contenu": contenu,
            "metadata": json.dumps(dict(top_pains[:5])),
            "sources_count": sum(c for _, c in top_pains),
            "confidence": 0.7,
        })

    return chunks


# ── Chunk 3 — Tendances et mots-clés du moment ───────────────────────────────

def _build_trend_chunks(messages: list[dict]) -> list[dict]:
    all_texts = [m["text"] for m in messages if m["text"]]
    if len(all_texts) < 10:
        return []

    keywords = compute_tfidf_keywords(all_texts, top_n=30)
    if not keywords:
        return []

    # Séparer par topic
    topic_texts: defaultdict[str, list] = defaultdict(list)
    for m in messages:
        for t in (m["topics"] or ["general"]):
            topic_texts[t].append(m["text"])

    chunks = []
    # Chunk global
    contenu = (
        f"TENDANCES DU MOMENT — Afrique de l'Ouest commerce informel\n"
        f"Mots et thèmes les plus discutés ({len(all_texts)} messages analysés) :\n\n"
        + "\n".join(f"• {w} (score: {round(s, 1)})" for w, s in keywords[:20])
    )
    chunks.append({
        "chunk_type": "tendances",
        "sujet": "global",
        "zone": "Afrique de l'Ouest",
        "periode": datetime.utcnow().strftime("%Y-%m"),
        "contenu": contenu,
        "metadata": json.dumps({w: round(s, 2) for w, s in keywords[:15]}),
        "sources_count": len(all_texts),
        "confidence": 0.75,
    })

    # Chunks par topic
    for topic, texts in topic_texts.items():
        if len(texts) < 5:
            continue
        kws = compute_tfidf_keywords(texts, top_n=15)
        if not kws:
            continue
        c = (
            f"TENDANCES — {topic.upper()}\n"
            f"Termes distinctifs ({len(texts)} messages) :\n"
            + ", ".join(w for w, _ in kws[:10])
        )
        chunks.append({
            "chunk_type": "tendances_topic",
            "sujet": topic,
            "zone": "Afrique de l'Ouest",
            "periode": datetime.utcnow().strftime("%Y-%m"),
            "contenu": c,
            "metadata": json.dumps({w: round(s, 2) for w, s in kws[:10]}),
            "sources_count": len(texts),
            "confidence": 0.65,
        })

    return chunks


# ── Chunk 4 — Sentiment marché par canal ─────────────────────────────────────

def _build_sentiment_chunks(messages: list[dict]) -> list[dict]:
    canal_sentiments: defaultdict[str, list] = defaultdict(list)
    for m in messages:
        if m["canal"] and m["sentiment"]:
            canal_sentiments[m["canal"]].append(m["sentiment"])

    chunks = []
    for canal, sentiments in canal_sentiments.items():
        if len(sentiments) < 5:
            continue
        counts = Counter(sentiments)
        total = len(sentiments)
        pos_pct = counts.get("positif", 0) / total * 100
        neg_pct = counts.get("negatif", 0) / total * 100

        mood = "optimiste" if pos_pct > 50 else "pessimiste" if neg_pct > 40 else "neutre"
        contenu = (
            f"AMBIANCE MARCHÉ — Canal : {canal}\n"
            f"Analyse de {total} messages :\n"
            f"• Positif : {pos_pct:.0f}%\n"
            f"• Négatif : {neg_pct:.0f}%\n"
            f"• Neutre  : {counts.get('neutre', 0) / total * 100:.0f}%\n"
            f"→ Ambiance générale : {mood}"
        )
        chunks.append({
            "chunk_type": "sentiment_canal",
            "sujet": canal,
            "zone": "Afrique de l'Ouest",
            "periode": datetime.utcnow().strftime("%Y-%m"),
            "contenu": contenu,
            "metadata": json.dumps(dict(counts)),
            "sources_count": total,
            "confidence": min(0.85, 0.5 + total / 100),
        })

    return chunks


# ── Store chunks ──────────────────────────────────────────────────────────────

def _store_chunks(chunks: list[dict], session) -> int:
    stored = 0
    for c in chunks:
        try:
            session.execute(sql_text("""
                INSERT INTO knowledge_chunks
                    (chunk_type, sujet, zone, periode, contenu, metadata, sources_count, confidence, updated_at)
                VALUES
                    (:ct, :sj, :zo, :pe, :co, :me, :sc, :cf, NOW())
                ON CONFLICT (chunk_type, sujet, zone, periode)
                DO UPDATE SET
                    contenu       = EXCLUDED.contenu,
                    metadata      = EXCLUDED.metadata,
                    sources_count = EXCLUDED.sources_count,
                    confidence    = EXCLUDED.confidence,
                    updated_at    = NOW()
            """), c)
            session.commit()
            stored += 1
        except Exception as e:
            session.rollback()
            logger.debug(f"chunk store error: {e}")
    return stored


# ── API publique ──────────────────────────────────────────────────────────────

def build_knowledge_base(session, days: int = 30) -> dict:
    """
    Pipeline complet : lit discussions_sociales → produit chunks → stocke.
    Retourne stats.
    """
    ensure_table(session)
    messages = _fetch_recent_discussions(session, days=days)
    logger.info(f"LLM Knowledge: {len(messages)} messages source")

    if not messages:
        return {"messages": 0, "chunks": 0}

    all_chunks = (
        _build_price_chunks(messages)
        + _build_pain_point_chunks(messages)
        + _build_trend_chunks(messages)
        + _build_sentiment_chunks(messages)
    )

    stored = _store_chunks(all_chunks, session)
    logger.info(f"LLM Knowledge: {stored} chunks produits/mis à jour")
    return {"messages": len(messages), "chunks": stored}


def get_market_context(session, sujet: str, zone: str = "Afrique de l'Ouest",
                       max_chunks: int = 5) -> str:
    """
    Retourne le contexte terrain pour un sujet donné.
    Utilisé par le frontend pour enrichir les réponses IA.
    """
    result = session.execute(sql_text("""
        SELECT contenu, chunk_type, confidence
        FROM knowledge_chunks
        WHERE (sujet ILIKE :sujet OR contenu ILIKE :sujet_like)
          AND zone = :zone
        ORDER BY confidence DESC, updated_at DESC
        LIMIT :max
    """), {"sujet": sujet, "sujet_like": f"%{sujet}%", "zone": zone, "max": max_chunks})

    rows = list(result)
    if not rows:
        return f"Aucun contexte terrain disponible pour '{sujet}'."

    parts = [f"[{r[1]}] {r[0]}" for r in rows]
    return "\n\n---\n\n".join(parts)


def get_price_intelligence(session, categorie: str) -> Optional[dict]:
    """Retourne les stats prix terrain pour une catégorie."""
    result = session.execute(sql_text("""
        SELECT metadata, sources_count, confidence, updated_at
        FROM knowledge_chunks
        WHERE chunk_type = 'prix_terrain'
          AND sujet ILIKE :cat
        ORDER BY updated_at DESC
        LIMIT 1
    """), {"cat": f"%{categorie}%"})
    row = result.fetchone()
    if not row:
        return None
    meta = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    return {**meta, "sources": row[1], "confidence": row[2], "updated": str(row[3])}
