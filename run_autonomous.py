"""
Runner autonome — Intelligence Commerciale AO.
Lance scraping complet + scoring + dedup + alertes + dashboard public.
Conçu pour tourner sans présence humaine (Task Scheduler Windows).

Usage :
  python run_autonomous.py           # run complet
  python run_autonomous.py --quick   # scraping rapide (sources fiables seulement)
  python run_autonomous.py --report  # rapport Telegram sans rescraper
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))

from dotenv import load_dotenv
load_dotenv(root / "config" / ".env")

from src.utils.config_loader import load_config
from src.utils.logger import setup_logger
from src.database.db import setup, stats_summary

logger = logging.getLogger(__name__)


def send_telegram(msg: str, config: dict):
    """Envoie un message Telegram."""
    import requests
    token   = os.getenv("TELEGRAM_TOKEN", "8645696626:AAF3MRlfOchJIz1jtCJ2hkakQv62o9vT8pM")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "5166710599")
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"Telegram: {e}")


def run_scraping(config: dict, quick: bool = False) -> dict:
    """Lance tous les scrapers. Retourne les compteurs."""
    results = {}

    # ── Sources rapides (requests, pas de browser) ──
    fast_sources = []
    if not quick:
        from src.scrapers.macro import world_bank, bceao, comtrade
        from src.scrapers.annuaires import kompass
        from src.scrapers import dakarois, europages, telegram_channels
        fast_sources += [
            ("world_bank",         world_bank),
            ("bceao",              bceao),
            ("comtrade",           comtrade),
            ("kompass",            kompass),
            ("dakarois",           dakarois),
            ("europages",          europages),
            ("telegram",           telegram_channels),
        ]

    # AOs toujours inclus
    from src.scrapers.ao import ungm, banque_mondiale, bad, dcmp
    fast_sources += [
        ("ungm",         ungm),
        ("banque_mondiale", banque_mondiale),
        ("bad",          bad),
        ("dcmp",         dcmp),
    ]

    for name, module in fast_sources:
        try:
            logger.info(f"Scraping: {name}")
            n = module.run(config)
            results[name] = n
            logger.info(f"  → {n} items")
        except Exception as e:
            logger.error(f"  ✗ {name}: {e}")
            results[name] = 0

    # ── Sources Playwright (browser) ──
    pw_sources = [
        ("coinafrique",    "src.scrapers.coinafrique_pw"),
        ("olx",            "src.scrapers.olx_pw"),
        ("facebook",       "src.scrapers.facebook_pw"),
        ("expat_dakar",    "src.scrapers.expat_dakar"),
    ]

    for name, module_path in pw_sources:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            logger.info(f"Scraping PW: {name}")
            n = mod.run(config)
            results[name] = n
            logger.info(f"  → {n} items")
        except Exception as e:
            logger.error(f"  ✗ {name} (PW): {e}")
            results[name] = 0

    return results


def run_dedup(config: dict) -> int:
    """Déduplication rapide post-scraping."""
    try:
        from src.analytics.deduplicator import run as dedup_run
        return dedup_run(config)
    except Exception as e:
        logger.error(f"Dedup: {e}")
        return 0


def run_score(config: dict) -> int:
    try:
        from src.scoring.scorer import scorer_tous_aos
        from src.database.models import get_session
        session = get_session(config)
        n = scorer_tous_aos(config, session)
        session.close()
        return n
    except Exception as e:
        logger.error(f"Scoring: {e}")
        return 0


def run_export(config: dict) -> str:
    try:
        from src.utils.exporters import export_rapport_complet
        from src.database.models import get_session
        session = get_session(config)
        path = export_rapport_complet(config, session)
        session.close()
        return path
    except Exception as e:
        logger.error(f"Export: {e}")
        return ""


def run_alerte(config: dict):
    try:
        from src.database.models import AppelOffre, get_session
        from src.alertes import email_alert
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
        if aos and "email" in config["alertes"].get("canaux", []):
            email_alert.envoyer_digest(aos, config)
        return len(aos)
    except Exception as e:
        logger.error(f"Alerte: {e}")
        return 0


def build_rapport(config, scraping_results: dict, nb_aos_scores: int, export_path: str) -> str:
    stats = stats_summary(config)
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")

    lines = [
        f"🌍 <b>Intel Commerciale AO — Run autonome</b>",
        f"📅 {ts}",
        "",
        f"<b>📊 Base de données :</b>",
        f"  • Produits : {stats['nb_produits']:,}",
        f"  • AOs actifs : {stats['nb_aos_actifs']}",
        f"  • 🔴 Prioritaires : {stats['ao_prioritaires']}",
        f"  • Informel : {stats['nb_informel']:,}",
        "",
        f"<b>🔄 Scraping :</b>",
    ]
    for src, n in scraping_results.items():
        emoji = "✅" if n > 0 else "⚠️"
        lines.append(f"  {emoji} {src}: {n}")

    lines += [
        "",
        f"<b>🎯 Scoring :</b> {nb_aos_scores} AOs scorés",
    ]
    if export_path:
        lines.append(f"<b>📁 Export :</b> {Path(export_path).name}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick",  action="store_true", help="Scraping rapide (AOs + informel seulement)")
    parser.add_argument("--report", action="store_true", help="Rapport Telegram seulement")
    parser.add_argument("--no-pw",  action="store_true", help="Pas de scrapers Playwright (headless)")
    args = parser.parse_args()

    config = load_config()
    setup_logger(config)
    setup(config)

    logger.info("=== RUN AUTONOME DEMARRE ===")
    send_telegram("Run autonome Intel Commerciale AO demarre...", config)

    if args.report:
        stats = stats_summary(config)
        send_telegram(f"📊 Stats actuelles:\n{stats}", config)
        return

    t0 = time.time()

    # 1. Scraping
    scraping_results = run_scraping(config, quick=args.quick)

    # 2. Déduplication
    nb_dedup = run_dedup(config)
    logger.info(f"Dedup: {nb_dedup} doublons supprimés")

    # 3. Scoring AOs
    nb_scores = run_score(config)

    # 4. Export Excel
    export_path = run_export(config)

    # 5. Alertes email
    nb_alertes = run_alerte(config)

    # 6. Rapport Telegram
    duree = int(time.time() - t0)
    rapport = build_rapport(config, scraping_results, nb_scores, export_path)
    rapport += f"\n\n⏱ Durée: {duree//60}min {duree%60}s"
    if nb_alertes:
        rapport += f"\n📧 {nb_alertes} AOs en alerte envoyés"

    send_telegram(rapport, config)
    logger.info("=== RUN AUTONOME TERMINE ===")
    safe = rapport.encode("ascii", errors="replace").decode("ascii")
    print(safe)


if __name__ == "__main__":
    main()
