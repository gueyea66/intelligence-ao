"""
Envoie un digest Telegram des meilleurs AOs du jour.
Utilise le token du bot Telegram existant (Bot control).
"""
import sys
import os
import requests
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None

# Importer config du bot existant
BOT_DIR = r"C:\Users\Abdou\Desktop\vadde meccum\Bot control"
sys.path.insert(0, BOT_DIR)
from config import settings

# Config DB intelligence-ao
INTEL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, INTEL_DIR)

env_path = os.path.join(INTEL_DIR, 'config', '.env')
with open(env_path, encoding='utf-8-sig') as f:
    for line in f:
        l = line.strip()
        if l and not l.startswith('#') and '=' in l:
            k, v = l.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'], connect_args={'sslmode': 'require'})

def get_top_aos(limit=10, score_min=70):
    with engine.connect() as conn:
        # Uniquement les AOs jamais notifies — chaque digest n'apporte que du neuf.
        # Priorite : date confirmee future, puis score, puis urgence.
        rows = conn.execute(text("""
            SELECT id, objet, entite, pays, score, jours_restants, url_source, date_limite
            FROM appels_offres
            WHERE score >= :score
              AND statut = 'actif'
              AND notifie_le IS NULL
              AND (date_limite >= NOW() OR date_limite IS NULL)
            ORDER BY
              CASE WHEN date_limite IS NOT NULL THEN 0 ELSE 1 END,
              score DESC,
              jours_restants ASC NULLS LAST
            LIMIT :lim
        """), {'score': score_min, 'lim': limit}).fetchall()
    return rows

def mark_notified(ids):
    if not ids:
        return
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE appels_offres SET notifie_le = NOW() WHERE id = ANY(:ids)"),
            {'ids': list(ids)},
        )
        conn.commit()

DASHBOARD_URL = "https://intelligence-ao.streamlit.app"

def format_message(aos):
    today = datetime.now().strftime('%d/%m/%Y')
    lines = [f"🎯 *Intel AO — {today}*", f"_{len(aos)} nouvelle(s) opportunité(s) score ≥ 70_", ""]
    for ao in aos:
        _id, objet, entite, pays, score, jours, url, date_limite = ao
        if jours is None:
            emoji = "⚪"
            delai = "date inconnue - verifier source"
        else:
            emoji = "🔴" if jours <= 7 else "🟡" if jours <= 14 else "🟢"
            delai = f"{jours}j restants"
        # Markdown v1 : un underscore non apparié casse tout le message (400 silencieux)
        objet = (objet or "—").replace("_", "-").replace("*", "")
        entite = (entite or "—").replace("_", "-").replace("*", "")
        titre = (objet[:55] + "…") if len(objet) > 55 else objet
        org = (entite[:30] + "…") if len(entite) > 30 else entite
        line = f"{emoji} *[{score}]* {titre}\n   📍 {pays} | {org} | {delai}"
        if url and url.startswith('http'):
            line += f"\n   🔗 [Voir →]({url})"
        lines.append(line)
        lines.append("")
    lines.append(f"🌐 [Dashboard →]({DASHBOARD_URL})")
    return "\n".join(lines)

def send(token, chat_id, text_msg):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": text_msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }, timeout=15)
    return resp.ok, resp.text

if __name__ == '__main__':
    aos = get_top_aos(limit=10, score_min=70)
    if not aos:
        today = datetime.now().strftime('%d/%m/%Y')
        msg = (f"🎯 *Intel AO — {today}*\n_Rien de nouveau au-dessus du seuil aujourd'hui._\n\n"
               f"🌐 [Dashboard →]({DASHBOARD_URL})")
    else:
        msg = format_message(aos)

    token = settings.telegram_token
    errors = []
    sent_ok = False
    for chat_id in settings.allowed_chat_ids:
        ok, resp = send(token, chat_id, msg)
        if ok:
            sent_ok = True
            print(f"  OK Telegram envoye a {chat_id}")
        else:
            print(f"  ERR chat {chat_id}: {resp[:100]}")
            errors.append(chat_id)

    # Marquer notifies seulement si au moins un envoi a reussi
    if aos and sent_ok:
        mark_notified([ao[0] for ao in aos])
        print(f"  {len(aos)} AOs marques notifie_le")

    sys.exit(1 if errors else 0)
