"""
One-shot: importe un export JSON Telegram Desktop dans discussions_sociales.
Usage: python scripts/import_tg_export.py <path_to_result.json>
"""
import json, os, re, hashlib, sys
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

DB_URL = os.environ["DATABASE_URL"]
JSON_PATH = sys.argv[1] if len(sys.argv) > 1 else "result.json"

engine = create_engine(DB_URL)

with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

canal_name = data.get("name", "COLOBANE_SANDAGA")
canal_id = f"tg_{data.get('id', canal_name)}"
messages = data.get("messages", [])

def analyze(text):
    lower = text.lower()
    prices = []
    for m in re.finditer(r'(\d[\d\s,.]*)\s*(fcfa|cfa|xof|f\b|francs?)', text, re.I):
        try:
            v = int(re.sub(r'[\s,.]','',m.group(1)))
            if 100 <= v <= 100_000_000: prices.append(v)
        except: pass
    pos = sum(1 for w in ['bon','bien','super','top','qualité','merci'] if w in lower)
    neg = sum(1 for w in ['arnaque','mauvais','cher','faux','problème'] if w in lower)
    topics = []
    if re.search(r'télépho|iphone|samsung|android', text, re.I): topics.append('electronique')
    if re.search(r'riz|huile|sucre|farine|viande|poisson', text, re.I): topics.append('alimentaire')
    if re.search(r'voiture|moto|transport', text, re.I): topics.append('transport')
    if re.search(r'appartement|maison|louer|location', text, re.I): topics.append('immobilier')
    if re.search(r'prix|vente|achat|vendre|acheter|commande', text, re.I): topics.append('commerce')
    if re.search(r'habit|robe|chaussure|mode', text, re.I): topics.append('textile')
    sent = 'positif' if pos > neg else 'negatif' if neg > pos else 'neutre'
    return sent, round((pos-neg)/5,2), prices, topics

inserted = skipped = 0
with engine.begin() as conn:
    for msg in messages:
        if msg.get("type") != "message": continue
        text = msg.get("text", "")
        if isinstance(text, list):
            text = " ".join(t if isinstance(t, str) else t.get("text","") for t in text)
        text = text.strip()
        if len(text) < 5: continue

        msg_id = str(msg.get("id",""))
        try:
            ts = datetime.fromisoformat(msg["date"]).replace(tzinfo=timezone.utc)
        except: continue

        sender = str(msg.get("from_id", msg.get("from", "unknown")))
        author_hash = hashlib.sha256(sender.encode()).hexdigest()
        sent, score, prices, topics = analyze(text)

        r = conn.execute(text("""
            INSERT INTO discussions_sociales
            (plateforme,canal,canal_id,message_id,texte_brut,date_publication,
             auteur_hash,sentiment,score_sentiment,topics,prix_mentionnes,
             contient_prix,contient_contact,type_message,traite)
            VALUES (:pl,:ca,:ci,:mi,:tb,:dp,:ah,:se,:ss,:to,:pr,:cp,:cc,:tm,:tr)
            ON CONFLICT (plateforme,canal_id,message_id) DO NOTHING
        """), dict(pl='telegram',ca=canal_name,ci=canal_id,mi=msg_id,tb=text,dp=ts,
                   ah=author_hash,se=sent,ss=score,to=json.dumps(topics),
                   pr=json.dumps(prices),cp=len(prices)>0,
                   cc=bool(re.search(r'\+?\d{8,}',text)),tm='message',tr=True))
        if r.rowcount: inserted += 1
        else: skipped += 1

print(f"Total: {len(messages)} msgs | Insérés: {inserted} | Doublons: {skipped}")
