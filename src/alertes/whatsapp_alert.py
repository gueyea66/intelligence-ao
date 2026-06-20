"""
Alertes WhatsApp via Twilio API.
Config : alertes.whatsapp dans config.yaml, TWILIO_* dans .env
"""
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def envoyer_digest_wa(aos: list, config: dict) -> bool:
    dest = config.get("alertes", {}).get("whatsapp") or os.getenv("ALERT_WHATSAPP", "")
    if not dest:
        logger.warning("WhatsApp non configuré (alertes.whatsapp ou ALERT_WHATSAPP)")
        return False

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_wa     = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    if not account_sid or not auth_token:
        logger.warning("Twilio non configuré (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN)")
        return False

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)

        top3 = aos[:3]
        lignes = "\n".join(
            f"• [{ao.score}] {ao.objet[:60]} — {ao.pays} ({ao.jours_restants}j)"
            for ao in top3
        )

        body = (
            f"🎯 *Intel AO — {datetime.now().strftime('%d/%m/%Y')}*\n"
            f"{len(aos)} opportunité(s) détectée(s)\n\n"
            f"Top opportunités :\n{lignes}"
        )

        client.messages.create(
            body=body,
            from_=from_wa,
            to=f"whatsapp:{dest}",
        )
        logger.info(f"WhatsApp envoyé à {dest}")
        return True

    except ImportError:
        logger.warning("twilio non installé. Ajouter 'twilio' à requirements.txt")
        return False
    except Exception as e:
        logger.error(f"Erreur WhatsApp: {e}")
        return False
