"""Connections: the module's own wellbeing.db and a read-only onboard.db."""

import sqlite3
import threading
from importlib.resources import files
from pathlib import Path

SCHEMA_VERSION = 1

_init_lock = threading.Lock()
_initialized: set[Path] = set()


def connect_wellbeing(db_path: Path) -> sqlite3.Connection:
    """Read/write connection to wellbeing.db, creating the schema on first use.

    The onboard app's lifespan is not ours to change, so the schema is created
    lazily, once per process and path.
    """
    resolved = db_path.resolve()
    with _init_lock:
        if resolved not in _initialized:
            init_wellbeing_db(db_path)
            _initialized.add(resolved)
    return _open(db_path)


def _open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_wellbeing_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _open(db_path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version != 0:
            raise RuntimeError(
                f"unsupported wellbeing schema version {version} in {db_path}; "
                f"expected {SCHEMA_VERSION}"
            )
        script = files("onboard_api.wellbeing").joinpath("schema.sql").read_text("utf-8")
        try:
            conn.executescript("BEGIN;\n" + script + "\nCOMMIT;")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


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
