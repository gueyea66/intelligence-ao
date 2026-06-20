"""
Configure Windows Task Scheduler — Intel Commerciale AO.
Utilise schtasks.exe (plus robuste que PowerShell pour chemins avec espaces).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT   = Path(__file__).parent
PYTHON = sys.executable

# Wrapper .bat pour éviter les problèmes de chemins avec espaces
BAT_DAILY   = ROOT / "run_daily.bat"
BAT_STARTUP = ROOT / "start_dashboard_public.bat"
BAT_WEEKLY  = ROOT / "run_weekly.bat"


def write_bats():
    """Crée les .bat d'entrée pour le scheduler."""
    bat_daily = f'@echo off\ncd /d "{ROOT}"\n"{PYTHON}" run_autonomous.py >> logs\\scheduler.log 2>&1\n'
    BAT_DAILY.write_text(bat_daily, encoding="utf-8")

    bat_weekly = f'@echo off\ncd /d "{ROOT}"\n"{PYTHON}" run_autonomous.py >> logs\\scheduler_weekly.log 2>&1\n'
    BAT_WEEKLY.write_text(bat_weekly, encoding="utf-8")

    # start_dashboard_public.bat existe déjà normalement
    if not BAT_STARTUP.exists():
        bat_startup = f'@echo off\ncd /d "{ROOT}"\n"{PYTHON}" startup_tunnel.py >> logs\\tunnel.log 2>&1\n'
        BAT_STARTUP.write_text(bat_startup, encoding="utf-8")

    # Créer dossier logs si absent
    (ROOT / "logs").mkdir(exist_ok=True)
    print("Fichiers .bat crees")


def schtask(name, bat_path, trigger_args):
    """Crée une tâche via schtasks.exe."""
    # Supprimer si existe déjà
    subprocess.run(
        ["schtasks", "/Delete", "/TN", name, "/F"],
        capture_output=True,
    )
    cmd = [
        "schtasks", "/Create",
        "/TN",  name,
        "/TR",  f'"{bat_path}"',
        "/RL",  "HIGHEST",
        "/F",
    ] + trigger_args

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="cp1252")
    if result.returncode == 0:
        print(f"  OK: {name}")
        return True
    else:
        err = (result.stdout + result.stderr).strip()[:300]
        print(f"  FAIL: {name}: {err}")
        return False


def main():
    print("Configuration Windows Task Scheduler - Intel Commerciale AO")
    print("=" * 60)

    write_bats()

    ok = 0

    # 1. Run quotidien à 05:30
    if schtask(
        "intel_ao_daily",
        BAT_DAILY,
        ["/SC", "DAILY", "/ST", "05:30"],
    ):
        ok += 1

    # 2. Dashboard au démarrage Windows (à la connexion)
    if schtask(
        "intel_ao_startup",
        BAT_STARTUP,
        ["/SC", "ONLOGON"],
    ):
        ok += 1

    # 3. Rapport hebdo lundi 07:00
    if schtask(
        "intel_ao_weekly",
        BAT_WEEKLY,
        ["/SC", "WEEKLY", "/D", "MON", "/ST", "07:00"],
    ):
        ok += 1

    print(f"\n{ok}/3 taches planifiees.")
    print("\nPlanning:")
    print("  intel_ao_daily   -> run complet chaque jour a 05:30")
    print("  intel_ao_startup -> dashboard + tunnel a chaque connexion Windows")
    print("  intel_ao_weekly  -> rapport hebdo lundi 07:00")
    print("\nVerifier: Panneau de configuration > Planificateur de taches")
    print("Logs: logs/scheduler.log")


if __name__ == "__main__":
    main()
