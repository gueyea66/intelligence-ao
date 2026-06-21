import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.data_quality.recategorizer import dry_run, run_migration
from src.database.models import get_session

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

config = {"database": {"type": "postgresql", "postgresql_url": db_url}}
session = get_session(config)

mode = sys.argv[1] if len(sys.argv) > 1 else "dry"
if mode == "apply":
    run_migration(session)
else:
    dry_run(session)

session.close()
