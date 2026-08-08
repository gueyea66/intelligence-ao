@echo off
cd /d "C:\Users\Abdou\Desktop\vadde meccum\Intelligence Commerciale Afrique de l'ouest\intelligence-ao"
set PYTHONIOENCODING=utf-8

echo [%date% %time%] === DEBUT SCAN QUOTIDIEN === >> logs\daily_scrapers.log

REM 1. Scraping toutes sources officielles (WB + BOAD + AfDB + MarchesDuSenegal)
python run_all_sources.py >> logs\daily_scrapers.log 2>&1
echo [%date% %time%] Sources scrapees >> logs\daily_scrapers.log

REM 2. Correction des dates et statuts
python fix_dates.py >> logs\daily_scrapers.log 2>&1

REM 3. Nettoyage encodage textes
python fix_encoding2.py >> logs\daily_scrapers.log 2>&1

REM 3b. Qualite des donnees : dedup, hors-scope, categories, informel, spam
python clean_data_quality.py >> logs\daily_scrapers.log 2>&1
echo [%date% %time%] Nettoyage qualite done >> logs\daily_scrapers.log

REM 4. Scoring ML
python -m src.ml.predict >> logs\daily_scrapers.log 2>&1
echo [%date% %time%] Scoring ML done >> logs\daily_scrapers.log

REM 4b. Snapshots historiques (scores AO + prix) — jamais d'ecrasement destructif
python snapshot_history.py >> logs\daily_scrapers.log 2>&1
echo [%date% %time%] Snapshots done >> logs\daily_scrapers.log

REM 4c. Context anchoring : contexte macro du jour soude aux observations
python macro_context.py >> logs\daily_scrapers.log 2>&1

REM 4d. Moteur d'alertes statistiques (z-score + spread formel/informel)
python detect_alertes.py >> logs\daily_scrapers.log 2>&1
echo [%date% %time%] Alertes detectees >> logs\daily_scrapers.log

REM 5. Alerte Telegram digest
python send_telegram_digest.py >> logs\daily_scrapers.log 2>&1
echo [%date% %time%] === FIN SCAN QUOTIDIEN === >> logs\daily_scrapers.log
