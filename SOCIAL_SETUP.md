# Setup Social Intelligence Pipeline

## 1. Telegram (PRIORITÉ HAUTE)

### Obtenir les clés API
1. Va sur https://my.telegram.org/apps
2. Connecte-toi avec ton numéro Telegram
3. Crée une app (nom quelconque)
4. Note **App api_id** et **App api_hash**

### Générer la session string (UNE FOIS)
```bash
pip install telethon
python -c "
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
api_id = int(input('api_id: '))
api_hash = input('api_hash: ')
with TelegramClient(StringSession(), api_id, api_hash) as client:
    print('SESSION_STRING:', client.session.save())
"
```
Scanne le QR code ou entre ton numéro.

### Configurer les secrets GitHub
```bash
gh secret set TELEGRAM_API_ID --body "TON_API_ID"
gh secret set TELEGRAM_API_HASH --body "TON_API_HASH"
gh secret set TELEGRAM_SESSION_STRING --body "TA_SESSION_STRING"
```

---

## 2. WhatsApp (ton numéro +221 78 760 03 30)

### Initialisation (UNE FOIS sur ton PC)
```bash
cd src/scrapers/social/whatsapp_scraper
npm install
node init_session.js
```
→ Scanne le QR code avec WhatsApp sur +221 78 760 03 30
→ Les groupes disponibles s'affichent dans `available_groups.json`

### Configurer les groupes cibles
Copie les IDs depuis `available_groups.json` vers `target_groups.json` :
```json
[
  {"id": "1234567890@g.us", "name": "Commerce Dakar"},
  {"id": "9876543210@g.us", "name": "Marchés Sénégal"}
]
```

### Compresser et uploader la session
```bash
tar -czf wa_session.tar.gz session_data/
# Windows PowerShell:
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("wa_session.tar.gz"))
gh secret set WHATSAPP_SESSION_B64 --body $b64
```

---

## 3. Facebook
Aucune configuration requise — scraping HTML pages publiques automatique.

---

## 4. GitHub Actions — Notification Telegram
Pour recevoir les notifications sur ton téléphone :
```bash
# Ton bot Telegram (si pas encore créé: @BotFather sur Telegram)
gh secret set TELEGRAM_BOT_TOKEN --body "ton_bot_token"
gh secret set TELEGRAM_CHAT_ID --body "ton_chat_id"
```
Ton chat_id : envoie un message à @userinfobot sur Telegram.

---

## 5. Documents institutionnels
```bash
pip install pdfplumber requests
python scripts/run_doc_scraper.py
```
Optionnel — UN Comtrade API (gratuit) :
```bash
# Inscription sur https://comtradeapi.un.org
gh secret set UN_COMTRADE_API_KEY --body "ta_cle"
```

---

## 6. Run manuel depuis le dashboard
Ajouter dans Vercel (dashboard.vercel.com) :
- `GITHUB_PAT` — Personal Access Token (scope: workflow) depuis github.com/settings/tokens
- `GITHUB_REPO` — `gueyea66/intelligence-ao` (ou ton repo)

→ Bouton "Run maintenant" dans le dashboard sur /intelligence

---

## 7. Crons actuels (GitHub Actions)
- **06h00 UTC** (6h Dakar) — Marché + Social
- **18h00 UTC** (18h Dakar) — Marché + Social + Documents
- **Manuel** — via GitHub Actions UI ou bouton dashboard
