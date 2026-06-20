"""
Parser de messages WhatsApp exportés (fichier .txt export WhatsApp).
Extrait les prix et produits mentionnés dans les groupes commerçants.
"""
import re
import logging
from datetime import datetime

from src.database.models import AnnoncInformel, get_session
from src.utils.config_loader import load_config

logger = logging.getLogger(__name__)

_PRIX_PATTERNS = [
    r"(\d[\d\s]{2,})\s*(F\s*CFA|FCFA|XOF|francs?)",
    r"(\d[\d\s]{2,})\s*(?:frs?|fr)\b",
    r"prix\s*:?\s*(\d[\d\s]{2,})",
]

_PRODUIT_KEYWORDS = [
    "vend", "disponible", "stock", "cherche", "besoin", "lot", "piece",
    "generateur", "groupe electrogene", "tissus", "textile", "riz", "sucre",
    "huile", "farine", "ciment", "fer", "tole", "telephones", "iphone",
    "samsung", "laptop", "ordinateur",
]


def parse_whatsapp_export(filepath: str, zone: str = "Dakar",
                          config: dict | None = None) -> int:
    """
    Parse un export WhatsApp (.txt) et insère les annonces détectées.
    Retourne le nombre d'annonces insérées.
    """
    if config is None:
        config = load_config()

    session = get_session(config)
    nb_ok   = 0

    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except FileNotFoundError:
        logger.error(f"Fichier non trouvé: {filepath}")
        return 0

    # Format WhatsApp : "DD/MM/YYYY, HH:MM - Nom: Message"
    msg_pattern = re.compile(
        r"(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2})(?:\s*[AP]M)?\s*[-–]\s*(.+?):\s*(.*)"
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = msg_pattern.match(line)
        if not m:
            continue

        date_str, time_str, sender, message = m.groups()
        message_low = message.lower()

        # Filtrer messages pertinents
        if not any(kw in message_low for kw in _PRODUIT_KEYWORDS):
            continue

        # Extraire prix
        prix = None
        for pat in _PRIX_PATTERNS:
            pm = re.search(pat, message, re.IGNORECASE)
            if pm:
                try:
                    prix = float(re.sub(r"\s", "", pm.group(1)))
                    break
                except ValueError:
                    pass

        # Détecter type offre/demande
        type_ann = "demande"
        if any(kw in message_low for kw in ["vend", "disponible", "stock", "lot", "prix"]):
            type_ann = "offre"

        try:
            ann = AnnoncInformel(
                source="WhatsApp",
                date_collecte=datetime.utcnow(),
                type=type_ann,
                produit=message[:200],
                marque="",
                prix_unitaire=prix,
                devise="XOF",
                vendeur_zone=zone,
                contact_disponible=True,
                notes_terrain=f"Source: {sender}",
            )
            session.add(ann)
            nb_ok += 1
        except Exception as e:
            logger.debug(f"WA parse insert: {e}")

    session.commit()
    session.close()
    logger.info(f"WhatsApp parser: {nb_ok} annonces extraites de {filepath}")
    return nb_ok
