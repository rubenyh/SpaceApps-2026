"""SQLite connection handling, migrations and timestamp encoding."""

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

# Versioned SQL files NNNN_<slug>.sql; NNNN is the user_version after applying it.
# Resolved from this file so it works from any launch directory (editable install).
MIGRATIONS_DIR = Path(__file__).resolve().parents[5] / "db" / "migrations" / "onboard"
_MIGRATION_NAME = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")

# Fixed width so lexicographic order in SQL equals chronological order.
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def to_db_timestamp(value: datetime) -> str:
    """Encode an aware datetime as a UTC fixed-width ISO 8601 string."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)


def from_db_timestamp(value: str) -> datetime:
    return datetime.strptime(value, _TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection in autocommit mode with the required pragmas.

    check_same_thread=False because FastAPI may open the connection in one
    worker thread and run the endpoint in another. Each connection is still
    used by one request at a time and closed when the request ends.
    """
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def load_migrations(migrations_dir: Path) -> list[tuple[int, str]]:
    """(version, sql) sorted by version. Versions must be 1..N without gaps."""
    if not migrations_dir.is_dir():
        raise RuntimeError(f"migrations directory not found: {migrations_dir}")
    migrations = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if not match:
            raise RuntimeError(f"invalid migration file name: {path.name} (want NNNN_slug.sql)")
        migrations.append((int(match[1]), path.read_text("utf-8")))
    versions = [version for version, _ in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise RuntimeError(f"migrations in {migrations_dir} must be numbered 1..N, got {versions}")
    return migrations


def _schema(conn: sqlite3.Connection) -> dict[str, object]:
    """Normalized schema: columns, foreign keys and indexes of every app table."""
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    schema: dict[str, object] = {}
    for table in tables:
        indexes = {}
        for index in conn.execute("SELECT * FROM pragma_index_list(?)", (table,)):
            indexes[index["name"]] = (
                index["unique"],
                index["origin"],
                [
                    (col["name"], col["desc"], col["coll"])
                    for col in conn.execute(
                        "SELECT * FROM pragma_index_xinfo(?) WHERE key = 1", (index["name"],)
                    )
                ],
            )
        schema[table] = {
            "columns": [
                (col["name"], col["type"].upper(), col["notnull"], col["dflt_value"], col["pk"])
                for col in conn.execute("SELECT * FROM pragma_table_info(?)", (table,))
            ],
            "foreign_keys": sorted(
                (fk["from"], fk["table"], fk["to"], fk["on_update"], fk["on_delete"])
                for fk in conn.execute("SELECT * FROM pragma_foreign_key_list(?)", (table,))
            ),
            "indexes": indexes,
        }
    return schema


def _baseline_legacy(conn: sqlite3.Connection, baseline_sql: str, db_path: Path) -> None:
    """Mark a pre-migrations DB (user_version 0 with tables) as version 1 if its
    schema matches 0001. Never changes schema or data."""
    reference = sqlite3.connect(":memory:")
    reference.row_factory = sqlite3.Row
    try:
        reference.executescript(baseline_sql)
        expected = _schema(reference)
    finally:
        reference.close()
    actual = _schema(conn)
    if actual != expected:
        diffs = [
            f"{table}: expected {expected.get(table)!r}, found {actual.get(table)!r}"
            for table in sorted(expected.keys() | actual.keys())
            if expected.get(table) != actual.get(table)
        ]
        raise RuntimeError(
            f"{db_path} has user_version 0 and tables that do not match migration 0001;"
            " not migrating. Differences: " + "; ".join(diffs)
        )
    conn.execute("PRAGMA user_version = 1")


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path, db_path: Path) -> None:
    migrations = load_migrations(migrations_dir)
    latest = len(migrations)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > latest:
        raise RuntimeError(
            f"{db_path} has schema version {version}, newer than the latest"
            f" migration {latest} in {migrations_dir}; update the code"
        )
    has_tables = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()
    if version == 0 and has_tables and migrations:
        _baseline_legacy(conn, migrations[0][1], db_path)
        version = 1
    for number, sql in migrations[version:]:
        try:
            # BEGIN goes inside the script because executescript commits any
            # open transaction first. The version bump commits with the DDL.
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    violations = conn.execute(
        "SELECT \"table\", count(*) FROM pragma_foreign_key_check GROUP BY \"table\" ORDER BY 1"
    ).fetchall()
    if violations:
        counts = ", ".join(f"{table}: {count}" for table, count in violations)
        raise RuntimeError(f"foreign key violations in {db_path}: {counts}")


def init_db(
    db_path: Path, now: datetime | None = None, migrations_dir: Path | None = None
) -> None:
    """Create the parent directory and apply pending migrations. `now` is unused
    (kept for existing callers); seed timestamps come from the migration SQL."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        apply_migrations(conn, migrations_dir or MIGRATIONS_DIR, db_path)
    finally:
        conn.close()
