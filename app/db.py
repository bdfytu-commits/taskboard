"""SQLite connection helpers and database initialisation."""
from pathlib import Path

import sqlite3
from flask import g


def get_db() -> sqlite3.Connection:
    """Return the request-scoped database connection."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_database(),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def current_database() -> str:
    from flask import current_app

    return current_app.config["DATABASE"]


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Create tables if they do not exist yet (idempotent)."""
    from flask import current_app

    db = get_db()
    schema = (Path(current_app.root_path) / "schema.sql").read_text(encoding="utf-8")
    db.executescript(schema)
    _migrate(db)
    db.commit()


def _migrate(db: sqlite3.Connection) -> None:
    """Лёгкие миграции для уже существующих баз."""
    cols = {r["name"] for r in db.execute("PRAGMA table_info(users)")}
    if "role" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
