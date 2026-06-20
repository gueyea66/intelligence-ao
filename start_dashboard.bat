@echo off
REM Lance le dashboard Streamlit
set PROJECT_DIR=C:\Users\Abdou\Desktop\vadde meccum\Intelligence Commerciale Afrique de l'ouest\intelligence-ao
cd /d "%PROJECT_DIR%"
echo Dashboard disponible sur http://localhost:8501
python -m streamlit run src/dashboard/app.py --server.headless false --server.port 8501
