@echo off
REM Lance le dashboard + tunnel Cloudflare public
set PROJECT_DIR=C:\Users\Abdou\Desktop\vadde meccum\Intelligence Commerciale Afrique de l'ouest\intelligence-ao
cd /d "%PROJECT_DIR%"

echo Demarrage du dashboard...
start "Dashboard" python -m streamlit run src/dashboard/app.py --server.port 8502 --server.headless true

timeout /t 5

echo Demarrage du tunnel public...
echo L'URL apparait ci-dessous en quelques secondes...
cloudflared tunnel --url http://localhost:8502
