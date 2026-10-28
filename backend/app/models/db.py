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

CREATE TABLE IF NOT EXISTS ors_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,               -- UTC ISO time
    endpoint TEXT NOT NULL,         -- matrix / directions
    caller TEXT NOT NULL,
    status INTEGER NOT NULL         -- HTTP status, 0 for a network error
);
CREATE INDEX IF NOT EXISTS ors_requests_ts ON ors_requests(ts);

CREATE TABLE IF NOT EXISTS ors_quota (
    endpoint TEXT PRIMARY KEY,
    remaining INTEGER,
    reset_at TEXT                   -- UTC ISO time
);

CREATE TABLE IF NOT EXISTS ors_cache (
    kind TEXT NOT NULL,             -- element / leg
    key TEXT NOT NULL,              -- route_key of the rounded points
    value TEXT NOT NULL,            -- JSON
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (kind, key)
);

-- What an invite shows publicly beyond the Invite model (plan places, explanations,
-- data sources), and what only the server may see (origins, owner keys, raw texts).
-- The private row is deleted when the invite expires.
CREATE TABLE IF NOT EXISTS invite_extra (
    token TEXT PRIMARY KEY,
    public TEXT NOT NULL,
    private TEXT
);

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


def save_invite(invite, path: Path | None = None) -> None:
    from datetime import datetime, timezone

    with connect(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO invites (token, status, created_at, expires_at, data)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                invite.token,
                invite.status,
                datetime.now(timezone.utc).isoformat(),
                invite.expires_at.isoformat(),
                invite.model_dump_json(),
            ),
        )


def load_invite(token: str, path: Path | None = None):
    from app.models.schemas import Invite

    with connect(path) as conn:
        row = conn.execute("SELECT data FROM invites WHERE token = ?", (token,)).fetchone()
    return Invite.model_validate_json(row["data"]) if row else None


def save_invite_extra(token: str, public: dict, private: dict | None, path: Path | None = None) -> None:
    import json

    with connect(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO invite_extra (token, public, private) VALUES (?, ?, ?)",
            (token, json.dumps(public), None if private is None else json.dumps(private)),
        )


def load_invite_extra(token: str, path: Path | None = None) -> tuple[dict, dict | None]:
    import json

    with connect(path) as conn:
        row = conn.execute("SELECT public, private FROM invite_extra WHERE token = ?", (token,)).fetchone()
    if not row:
        return {}, None
    return json.loads(row["public"]), (json.loads(row["private"]) if row["private"] else None)
