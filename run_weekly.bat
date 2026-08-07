@echo off
cd /d "C:\Users\Abdou\Desktop\vadde meccum\Intelligence Commerciale Afrique de l'ouest\intelligence-ao"
set PYTHONIOENCODING=utf-8

echo [%date% %time%] === DEBUT SCAN HEBDOMADAIRE === >> logs\weekly_scrapers.log

REM 1. Run complet toutes sources (même que quotidien mais inclus ici aussi)
python run_all_sources.py >> logs\weekly_scrapers.log 2>&1

REM 2. Fix dates + encodage
python fix_dates.py >> logs\weekly_scrapers.log 2>&1
python fix_encoding2.py >> logs\weekly_scrapers.log 2>&1

REM 3. Re-entraîner le modèle ML sur l'historique cumulé
python -m src.ml.train >> logs\ml_train.log 2>&1
echo [%date% %time%] ML retrain done >> logs\ml_train.log

REM 4. Scoring ML avec nouveau modèle
python -m src.ml.predict >> logs\weekly_scrapers.log 2>&1

REM 5. Scrapers marche informel (Jumia + Expat-Dakar + CoinAfrique + Auchan -> produits)
python run_scrapers.py >> logs\weekly_scrapers.log 2>&1
echo [%date% %time%] Scrapers informel done >> logs\weekly_scrapers.log

REM 6. Bulletin hebdo si disponible
python bulletin_prix.py >> logs\bulletin.log 2>&1

echo [%date% %time%] === FIN SCAN HEBDOMADAIRE === >> logs\weekly_scrapers.log
