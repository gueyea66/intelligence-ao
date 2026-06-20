"""Charge config.yaml depuis le dossier config/ à la racine du projet."""
import os
from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).parent.parent.parent / "config" / "config.yaml"


def load_config(path: str | None = None) -> dict:
    config_path = Path(path) if path else _DEFAULT_PATH
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
