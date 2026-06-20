"""Point d'entrée Streamlit Cloud — initialise la DB si absente puis lance le dashboard."""
import os
import sys
from pathlib import Path

# Init DB si elle n'existe pas (premier démarrage sur Streamlit Cloud)
db_path = Path("data/intelligence.db")
db_path.parent.mkdir(exist_ok=True)

if not db_path.exists():
    from src.utils.config_loader import load_config
    from src.database.db import setup
    setup(load_config())

# Charger le dashboard
exec(open("src/dashboard/app.py").read())
