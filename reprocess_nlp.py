"""Re-applique le NLP sur tous les messages sans topics dans discussions_sociales."""
import os, json
from pathlib import Path

for line in Path("config/.env").read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if line and "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import create_engine, text
from src.analytics.nlp_engine import analyze_message

engine = create_engine(os.environ["DATABASE_URL"], connect_args={"sslmode": "require"})

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT id, texte_brut FROM discussions_sociales "
        "WHERE (topics IS NULL OR topics = '[]'::jsonb) "
        "AND texte_brut IS NOT NULL AND LENGTH(texte_brut) > 5"
    )).fetchall()

    print(f"Messages à retraiter: {len(rows)}")
    updated = 0

    for row_id, texte in rows:
        try:
            nlp = analyze_message(texte)
            conn.execute(text("""
                UPDATE discussions_sociales SET
                    langue           = :la,
                    sentiment        = :se,
                    score_sentiment  = :ss,
                    topics           = :to,
                    pain_points      = :pp,
                    prix_mentionnes  = :pr,
                    contient_prix    = :cp,
                    contient_contact = :cc,
                    type_message     = :tm,
                    traite           = TRUE
                WHERE id = :id
            """), {
                "la": nlp.get("langue", "fr"),
                "se": nlp["sentiment"],
                "ss": nlp["score_sentiment"],
                "to": json.dumps(nlp["topics"]),
                "pp": json.dumps(nlp.get("pain_points", [])),
                "pr": json.dumps([p["montant"] for p in nlp.get("prix_mentionnes", [])]),
                "cp": nlp["contient_prix"],
                "cc": nlp["contient_contact"],
                "tm": nlp.get("type_message", "message"),
                "id": row_id,
            })
            updated += 1
            if updated % 20 == 0:
                conn.commit()
                print(f"  {updated}/{len(rows)} traites...")
        except Exception as ex:
            print(f"  Erreur id={row_id}: {ex}")

    conn.commit()
    print(f"Done — {updated} messages mis a jour")
