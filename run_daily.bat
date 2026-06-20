@echo off
REM Script de collecte quotidienne — Intelligence Commerciale AO
REM A planifier dans le Planificateur de taches Windows (Task Scheduler)

set PROJECT_DIR=C:\Users\Abdou\Desktop\vadde meccum\Intelligence Commerciale Afrique de l'ouest\intelligence-ao
cd /d "%PROJECT_DIR%"

echo [%date% %time%] Demarrage collecte quotidienne >> logs\scheduler.log

python main.py scrape >> logs\scheduler.log 2>&1
python main.py score  >> logs\scheduler.log 2>&1
python main.py export >> logs\scheduler.log 2>&1
python main.py alerte >> logs\scheduler.log 2>&1

echo [%date% %time%] Collecte terminee >> logs\scheduler.log
