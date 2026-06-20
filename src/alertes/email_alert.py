"""
Alertes email — envoi digest quotidien des AOs prioritaires.
Config : alertes.email dans config.yaml, SMTP_* dans .env
"""
import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)


def envoyer_digest(aos: list, config: dict) -> bool:
    """
    Envoie un digest HTML des AOs prioritaires.
    Retourne True si envoyé avec succès.
    """
    alerte_cfg = config.get("alertes", {})
    dest_email  = alerte_cfg.get("email") or os.getenv("ALERT_EMAIL", "")

    if not dest_email:
        logger.warning("Email d'alerte non configuré (alertes.email dans config.yaml ou ALERT_EMAIL dans .env)")
        return False

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        logger.warning("SMTP non configuré (SMTP_USER / SMTP_PASS dans .env)")
        return False

    if not aos:
        logger.info("Aucun AO à envoyer")
        return True

    sujet = f"[Intelligence AO] {len(aos)} opportunité(s) — {datetime.now().strftime('%d/%m/%Y')}"
    corps_html = _build_html(aos, config)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = sujet
    msg["From"]    = smtp_user
    msg["To"]      = dest_email
    msg.attach(MIMEText(corps_html, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, dest_email, msg.as_string())
        logger.info(f"Email envoyé à {dest_email} — {len(aos)} AOs")
        return True
    except Exception as e:
        logger.error(f"Erreur envoi email: {e}")
        return False


def _build_html(aos: list, config: dict) -> str:
    seuil_haute = config["scoring"]["seuils"]["priorite_haute"]

    lignes = ""
    for ao in aos:
        couleur = "#d32f2f" if (ao.score or 0) >= seuil_haute else "#f57c00"
        lignes += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee;">
            <strong style="color:{couleur};">{ao.score or '—'}</strong>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;">{ao.source}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">
            <a href="{ao.url_source or '#'}">{ao.objet or '—'}</a>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;">{ao.pays}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">{ao.jours_restants or '—'}j</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">{ao.positionnement or '—'}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:900px;margin:auto;">
    <h2 style="color:#1565c0;">🎯 Intelligence Commerciale — Digest AO</h2>
    <p style="color:#555;">{datetime.now().strftime('%d %B %Y')} — {len(aos)} opportunité(s)</p>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#1565c0;color:white;">
          <th style="padding:10px;">Score</th>
          <th style="padding:10px;">Source</th>
          <th style="padding:10px;">Objet</th>
          <th style="padding:10px;">Pays</th>
          <th style="padding:10px;">Délai</th>
          <th style="padding:10px;">Positionnement</th>
        </tr>
      </thead>
      <tbody>{lignes}</tbody>
    </table>
    <p style="color:#999;font-size:12px;margin-top:20px;">
      Intelligence Commerciale Afrique de l'Ouest — automated by claude code
    </p>
    </body></html>"""


def envoyer_alerte_immediate(ao, config: dict) -> bool:
    """Alerte immédiate pour un AO score > seuil_haute."""
    return envoyer_digest([ao], config)
