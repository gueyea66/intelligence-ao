"""
Démarrage automatique : dashboard Streamlit + tunnel Cloudflare + notification Telegram.
Planifié au démarrage Windows via Task Scheduler.
"""
import subprocess
import time
import re
import sys
import requests
import os

TELEGRAM_TOKEN   = "8645696626:AAF3MRlfOchJIz1jtCJ2hkakQv62o9vT8pM"
TELEGRAM_CHAT_ID = "5166710599"
PROJECT_DIR      = os.path.dirname(os.path.abspath(__file__))
PYTHON           = sys.executable
CLOUDFLARED      = r"C:\Users\Abdou\AppData\Local\Microsoft\WinGet\Links\cloudflared.exe"
DASHBOARD_PORT   = 8503  # port dédié au tunnel public


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)


def main():
    os.chdir(PROJECT_DIR)

    # 1. Lancer dashboard Streamlit en arrière-plan
    send_telegram("🚀 <b>Intel AO</b> — Démarrage du dashboard...")
    dashboard = subprocess.Popen(
        [PYTHON, "-m", "streamlit", "run", "src/dashboard/app.py",
         "--server.port", str(DASHBOARD_PORT), "--server.headless", "true"],
        cwd=PROJECT_DIR,
    )
    time.sleep(8)

    # 2. Lancer tunnel Cloudflare et capturer l'URL
    tunnel_log = os.path.join(PROJECT_DIR, "tunnel.log")
    with open(tunnel_log, "w") as f:
        tunnel = subprocess.Popen(
            [CLOUDFLARED, "tunnel", "--url", f"http://localhost:{DASHBOARD_PORT}"],
            stderr=f, stdout=f,
            cwd=PROJECT_DIR,
        )

    # Attendre l'URL (max 30s)
    url = None
    for _ in range(30):
        time.sleep(1)
        try:
            content = open(tunnel_log).read()
            match = re.search(r"https://[\w-]+\.trycloudflare\.com", content)
            if match:
                url = match.group(0)
                break
        except Exception:
            pass

    # 3. Envoyer l'URL sur Telegram
    if url:
        send_telegram(
            f"✅ <b>Intel AO Dashboard</b> en ligne\n\n"
            f"🔗 <a href='{url}'>{url}</a>\n\n"
            f"Accessible depuis ton téléphone."
        )
    else:
        send_telegram("⚠️ <b>Intel AO</b> — Tunnel démarré mais URL non détectée. Vérifier tunnel.log")

    # Garder le processus tunnel actif
    tunnel.wait()


if __name__ == "__main__":
    main()
