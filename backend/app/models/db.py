import sqlite3
from pathlib import Path

from app.core.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta_spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,              -- UTC date, YYYY-MM-DD
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,             -- text / image / voice
    model TEXT NOT NULL,
    cost_usd REAL NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS meta_spend_day ON meta_spend(day);

CREATE TABLE IF NOT EXISTS invites (
    token TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    data TEXT NOT NULL              -- Invite JSON
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or get_settings().db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
