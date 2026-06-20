# Intelligence Commerciale — Afrique de l'Ouest

Machine d'intelligence commerciale couvrant les marchés formel et informel d'Afrique de l'Ouest.

---

## Démarrage rapide

```bash
# 1. Installer les dépendances
pip install -r requirements.txt
python -m playwright install chromium

# 2. Initialiser la base
python main.py init

# 3. Collecter les données
python main.py scrape

# 4. Scorer les AOs
python main.py score

# 5. Ouvrir le dashboard
python -m streamlit run src/dashboard/app.py
```

Dashboard disponible sur **http://localhost:8501**

---

## Commandes CLI

| Commande | Description |
|---|---|
| `python main.py init` | Initialise la base SQLite |
| `python main.py scrape` | Collecte toutes les sources actives |
| `python main.py scrape --source ao` | Collecte AOs uniquement |
| `python main.py scrape --source ecommerce` | Collecte e-commerce uniquement |
| `python main.py scrape --source informel` | Collecte annonces informel |
| `python main.py scrape --source macro` | Collecte données Comtrade |
| `python main.py score` | Score tous les AOs non scorés |
| `python main.py export` | Export Excel multi-onglets |
| `python main.py alerte` | Envoie digest email/WhatsApp |
| `python main.py run` | Pipeline complet (scrape+score+export+alerte) |
| `python main.py schedule` | Scheduler automatique |
| `python main.py dashboard` | Lance le dashboard |

---

## Configuration

Tout est dans **`config/config.yaml`** — aucune valeur hardcodée dans le code.

```yaml
# Activer/désactiver une source
sources:
  ecommerce:
    - nom: "Jumia Sénégal"
      actif: true          # ← changer ici
      frequence: "hebdomadaire"

# Modifier les poids du scoring
scoring:
  poids:
    pertinence_sectorielle: 25   # ← ajustable
    taille_marche: 20

# Configurer les alertes
alertes:
  canaux: ["email", "whatsapp"]
  score_minimum_alerte: 70
```

Secrets dans **`config/.env`** :
```env
ALERT_EMAIL=ton@email.com
SMTP_USER=ton@gmail.com
SMTP_PASS=mot_de_passe_app
ALERT_WHATSAPP=+221XXXXXXXXX
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
```

---

## Sources couvertes

### E-commerce
| Source | Statut | Fréquence |
|---|---|---|
| Jumia Sénégal | ✅ Actif | Hebdo |
| Auchan Sénégal | ✅ Actif | Hebdo |
| CoinAfrique SN | ✅ Actif | Quotidien |
| Jotay.net | ✅ Actif | Quotidien |
| Facebook Marketplace | ✅ Actif | Quotidien |

### Appels d'Offres
| Source | Statut | Périmètre |
|---|---|---|
| DCMP Sénégal | ✅ Actif | Marchés publics SN |
| UNGM | ✅ Actif | Agences ONU |
| DgMarket | ✅ Actif | International |
| Banque Mondiale | ✅ Actif | Projets BM |
| BAD | ✅ Actif | Projets BAD |
| DGMP Mali | ⏸ Inactif | Marchés publics ML |
| DGF Côte d'Ivoire | ⏸ Inactif | Marchés publics CI |

### Macro
| Source | Statut |
|---|---|
| UN Comtrade | ✅ Actif |

---

## Scoring AOs

Le score est calculé sur 6 critères (total 100 points) :

| Critère | Poids | Description |
|---|---|---|
| Pertinence sectorielle | 25 | Adéquation avec secteurs cibles |
| Taille du marché | 20 | Budget estimé |
| Délai de réponse | 15 | Jours restants avant clôture |
| Accessibilité géo | 15 | Proximité du marché |
| Disponibilité fournisseur | 15 | Facilité de sourcing |
| Niveau concurrence | 10 | Concurrence locale estimée |

**Niveaux :**
- 🔴 > 70 : PRIORITÉ HAUTE — alerte immédiate
- 🟡 40-70 : À SURVEILLER — revue hebdomadaire
- ⚪ < 40 : ARCHIVÉ

---

## Module Informel

### Sources automatiques
- Facebook Marketplace Dakar
- CoinAfrique Sénégal
- Jotay.net

### Saisie terrain
Depuis le dashboard onglet "Marché Informel" → formulaire de saisie.

### Import WhatsApp
```python
from src.utils.whatsapp_parser import parse_whatsapp_export
parse_whatsapp_export("export_whatsapp.txt", zone="Sandaga")
```

---

## Automatisation (Windows)

La tâche planifiée **`IntelCommerciale_Daily`** est créée automatiquement.
Elle s'exécute chaque jour à **06h00** et lance le pipeline complet.

Vérifier dans le Planificateur de tâches Windows ou via :
```
schtasks /Query /TN "IntelCommerciale_Daily"
```

---

## Architecture

```
intelligence-ao/
├── config/
│   ├── config.yaml          ← Configuration maître
│   └── .env                 ← Secrets (non versionné)
├── src/
│   ├── scrapers/            ← 10 scrapers
│   │   ├── ao/              ← 5 scanners AO
│   │   └── macro/           ← Données Comtrade
│   ├── database/            ← SQLAlchemy ORM
│   ├── scoring/             ← Moteur scoring 6 critères
│   ├── alertes/             ← Email + WhatsApp
│   ├── dashboard/           ← Streamlit 4 onglets
│   └── utils/               ← Config, logger, export, WA parser
├── data/intelligence.db     ← Base SQLite locale
├── exports/                 ← Rapports Excel
├── logs/                    ← Logs rotatifs
├── main.py                  ← CLI principal
├── run_daily.bat            ← Script planification Windows
└── start_dashboard.bat      ← Lancement dashboard
```

---

## Stack technique

- **Python 3.11+**
- **SQLAlchemy** — ORM (SQLite MVP → PostgreSQL production)
- **BeautifulSoup4 + Playwright** — Scraping HTML + JS dynamique
- **Streamlit** — Dashboard
- **pandas + openpyxl** — Export Excel
- **schedule** — Scheduler Python
- **smtplib / Twilio** — Alertes

---

*Intelligence Commerciale Afrique de l'Ouest — Sprint 1-2 MVP*
*Généré automatiquement — Juin 2026*
