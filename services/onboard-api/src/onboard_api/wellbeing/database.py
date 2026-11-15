"""Connections: the module's own wellbeing.db and a read-only onboard.db."""

import sqlite3
import threading
from pathlib import Path

from onboard_api.repositories.database import connect, init_db

# db/migrations/wellbeing at the repo root, resolved from this file like the
# onboard MIGRATIONS_DIR, so it works from any launch directory.
WELLBEING_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[5] / "db" / "migrations" / "wellbeing"
)

_init_lock = threading.Lock()
_initialized: set[Path] = set()


def connect_wellbeing(db_path: Path) -> sqlite3.Connection:
    """Read/write connection to wellbeing.db, migrating it on first use.

    The onboard app's lifespan is not ours to change, so migrations run
    lazily, once per process and path.
    """
    resolved = db_path.resolve()
    with _init_lock:
        if resolved not in _initialized:
            init_db(db_path, migrations_dir=WELLBEING_MIGRATIONS_DIR)
            _initialized.add(resolved)
    return connect(db_path)


class OnboardDatabaseUnavailable(Exception):
    pass


def connect_onboard_readonly(db_path: Path) -> sqlite3.Connection:
    """Read-only connection to the onboard service's database.

    mode=ro never creates or modifies the file. The onboard DB uses WAL, so
    reading while the onboard service writes is safe.
    """
    if not db_path.exists():
        raise OnboardDatabaseUnavailable(f"onboard database not found at {db_path}")
    uri = db_path.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    except sqlite3.OperationalError as exc:
        raise OnboardDatabaseUnavailable(str(exc)) from exc
    conn.row_factory = sqlite3.Row
    return conn
