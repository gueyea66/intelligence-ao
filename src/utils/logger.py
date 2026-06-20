"""Logger centralisé avec rotation quotidienne."""
import logging
import logging.handlers
import os
from pathlib import Path


def setup_logger(config: dict) -> None:
    log_cfg = config.get("logging", {})
    niveau  = getattr(logging, log_cfg.get("niveau", "INFO"), logging.INFO)
    dossier = log_cfg.get("dossier", "./logs")
    retention = log_cfg.get("retention_jours", 30)

    Path(dossier).mkdir(parents=True, exist_ok=True)
    log_file = os.path.join(dossier, "intelligence.log")

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(niveau)

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    root.addHandler(ch)

    # Fichier avec rotation quotidienne
    fh = logging.handlers.TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=retention, encoding="utf-8"
    )
    fh.setFormatter(formatter)
    root.addHandler(fh)
