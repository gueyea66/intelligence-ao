"""
Intelligence Commerciale Afrique de l'Ouest — Point d'entrée CLI.

Usage :
  python main.py init                         # initialise la base
  python main.py scrape                       # scrape toutes les sources actives
  python main.py scrape --source ao           # scrape AOs uniquement
  python main.py scrape --source ecommerce    # scrape e-commerce uniquement
  python main.py scrape --source informel     # scrape annonces informel
  python main.py score                        # score tous les AOs non scorés
  python main.py export                       # exporte tout en Excel
  python main.py alerte                       # envoie digest email AOs prioritaires
  python main.py run                          # run complet (scrape + score + export + alerte)
  python main.py dashboard                    # lance le dashboard Streamlit
  python main.py schedule                     # lance le scheduler automatique
"""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "config", ".env"))

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from src.utils.config_loader import load_config
from src.utils.logger import setup_logger
from src.database.db import setup
from src.database.models import get_session

logger = logging.getLogger(__name__)


def cmd_init(config):
    setup(config)
    logger.info("Base de données initialisée.")
    print("✅ Base initialisée")


def cmd_scrape(config, source_filter=None):
    from src.scrapers import jumia, auchan
    from src.scrapers import facebook_marketplace, jotay, coinafrique
    from src.scrapers import expat_dakar, olx_senegal, dakarois, europages, telegram_channels
    from src.scrapers import coinafrique_pw, olx_pw, facebook_pw
    from src.scrapers.ao import dcmp, ungm, dgmarket, banque_mondiale, bad
    from src.scrapers.macro import comtrade, world_bank, bceao
    from src.scrapers.annuaires import kompass

    sources_ao = [
        ("ao", dcmp),
        ("ao", ungm),
        ("ao", dgmarket),
        ("ao", banque_mondiale),
        ("ao", bad),
    ]
    sources_ecommerce = [
        ("ecommerce", jumia),
        ("ecommerce", auchan),
    ]
    sources_macro = [
        ("macro", comtrade),
        ("macro", world_bank),
        ("macro", bceao),
    ]
    sources_informel = [
        ("informel", expat_dakar),
        ("informel", dakarois),
        ("informel", telegram_channels),
        ("informel", coinafrique_pw),   # Playwright
        ("informel", olx_pw),           # Playwright
        ("informel", facebook_pw),      # Playwright + profil Chrome
    ]

    # Sources sociales (Telegram public + WhatsApp exports)
    from src.scrapers.social import telegram_bot_scraper, whatsapp_scraper
    sources_social = [
        ("social", telegram_bot_scraper),
        ("social", whatsapp_scraper),
    ]
    sources_annuaires = [
        ("annuaires", kompass),
        ("annuaires", europages),
    ]

    all_sources = sources_ao + sources_ecommerce + sources_informel + sources_macro + sources_annuaires + sources_social
    if source_filter:
        all_sources = [(t, m) for t, m in all_sources if t == source_filter]

    total = 0
    for type_, module in all_sources:
        logger.info(f"Démarrage: {module.__name__}")
        try:
            n = module.run(config)
            total += n
            logger.info(f"  → {n} items")
        except Exception as e:
            logger.error(f"Erreur {module.__name__}: {e}", exc_info=True)

    print(f"✅ Scraping terminé — {total} items collectés")
    return total


def cmd_score(config):
    from src.scoring.scorer import scorer_tous_aos
    session = get_session(config)
    n = scorer_tous_aos(config, session)
    session.close()
    print(f"✅ {n} AOs scorés")
    return n


def cmd_export(config):
    from src.utils.exporters import export_rapport_complet
    session = get_session(config)
    path = export_rapport_complet(config, session)
    session.close()
    print(f"✅ Rapport exporté : {path}")
    return path


def cmd_alerte(config):
    from src.database.models import AppelOffre
    from src.alertes import email_alert, whatsapp_alert
    from datetime import datetime

    session = get_session(config)
    seuil = config["alertes"].get("score_minimum_alerte", 70)

    aos = (
        session.query(AppelOffre)
        .filter(AppelOffre.score >= seuil)
        .filter(AppelOffre.date_limite >= datetime.utcnow())
        .order_by(AppelOffre.score.desc())
        .limit(20)
        .all()
    )
    session.close()

    if not aos:
        print("Aucun AO au-dessus du seuil d'alerte")
        return

    canaux = config["alertes"].get("canaux", [])
    if "email" in canaux:
        email_alert.envoyer_digest(aos, config)
    if "whatsapp" in canaux:
        whatsapp_alert.envoyer_digest_wa(aos, config)

    print(f"✅ Alertes envoyées pour {len(aos)} AOs")


def cmd_knowledge(config):
    """Construit la base de connaissance LLM depuis discussions_sociales."""
    from src.pipeline.llm_knowledge import build_knowledge_base
    session = get_session(config)
    stats = build_knowledge_base(session, days=30)
    session.close()
    print(f"✅ Knowledge base: {stats['chunks']} chunks produits depuis {stats['messages']} messages")


def cmd_social(config):
    """Scrape social complet : Telegram public + WhatsApp exports → Supabase."""
    from src.scrapers.social import telegram_bot_scraper, whatsapp_scraper
    session = get_session(config)
    n_tg = telegram_bot_scraper.scrape(session, days_back=7)
    n_wa = whatsapp_scraper.scrape(session)
    session.close()
    print(f"✅ Social: {n_tg} msgs Telegram + {n_wa} msgs WhatsApp insérés")
    # Rebuild knowledge base après chaque scrape social
    from src.pipeline.llm_knowledge import build_knowledge_base
    session2 = get_session(config)
    stats = build_knowledge_base(session2, days=30)
    session2.close()
    print(f"✅ Knowledge base mise à jour: {stats['chunks']} chunks")


def cmd_run(config):
    """Run complet : scrape → social → score → knowledge → export → alerte."""
    logger.info("=== RUN COMPLET ===")
    cmd_scrape(config)
    cmd_social(config)
    cmd_score(config)
    cmd_knowledge(config)
    cmd_export(config)
    cmd_alerte(config)
    logger.info("=== FIN RUN COMPLET ===")


def cmd_dashboard(config):
    import subprocess
    dashboard_path = os.path.join(os.path.dirname(__file__), "src", "dashboard", "app.py")
    print(f"🚀 Lancement dashboard : http://localhost:8501")
    subprocess.run([sys.executable, "-m", "streamlit", "run", dashboard_path], check=True)


def cmd_schedule(config):
    import schedule as sched
    import time

    freq = config["alertes"].get("frequence_digest", "quotidien")
    logger.info(f"Scheduler démarré — fréquence: {freq}")
    print(f"⏰ Scheduler actif — fréquence: {freq}")
    print("   Ctrl+C pour arrêter")

    def job():
        logger.info("Scheduled job démarré")
        cmd_run(config)

    if freq == "quotidien":
        sched.every().day.at("06:00").do(job)
    elif freq == "hebdomadaire":
        sched.every().monday.at("07:00").do(job)
    else:
        sched.every().hour.do(job)

    # Premier run immédiat
    job()

    while True:
        sched.run_pending()
        time.sleep(60)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Intelligence Commerciale Afrique de l'Ouest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        choices=["init", "scrape", "score", "export", "alerte", "run",
                 "dashboard", "schedule", "social", "knowledge"],
        help="Commande à exécuter",
    )
    parser.add_argument(
        "--source",
        choices=["ao", "ecommerce", "informel", "macro", "annuaires", "social"],
        help="Filtre source pour scrape",
    )
    parser.add_argument(
        "--days",
        type=int, default=7,
        help="Nombre de jours en arrière pour social/knowledge",
    )
    parser.add_argument(
        "--config",
        help="Chemin vers config.yaml (défaut: config/config.yaml)",
    )

    args = parser.parse_args()

    config = load_config(args.config)
    setup_logger(config)

    if args.command == "init":
        cmd_init(config)
    elif args.command == "scrape":
        cmd_scrape(config, source_filter=args.source)
    elif args.command == "score":
        cmd_score(config)
    elif args.command == "export":
        cmd_export(config)
    elif args.command == "alerte":
        cmd_alerte(config)
    elif args.command == "run":
        cmd_run(config)
    elif args.command == "social":
        cmd_social(config)
    elif args.command == "knowledge":
        cmd_knowledge(config)
    elif args.command == "dashboard":
        cmd_dashboard(config)
    elif args.command == "schedule":
        cmd_schedule(config)


if __name__ == "__main__":
    main()
