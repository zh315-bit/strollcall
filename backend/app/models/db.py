"""Persistent storage: Postgres when DATABASE_URL is set (deployed, Neon), SQLite otherwise
(local development and tests, offline).

SQL is written once with `?` placeholders and `ON CONFLICT ... DO UPDATE` upserts, which both
engines accept; only the DDL differs. Tables are created on first use (idempotent DDL, no
migration framework). On Postgres a small pool (max 5) is used, prepared statements are off
(Neon's pooled endpoint runs PgBouncer in transaction mode), and a statement is retried once on
a connection error, because a Neon compute that scaled to zero takes a moment to wake.
"""

import logging
import sqlite3
import threading
from pathlib import Path

from app.core.config import get_settings

log = logging.getLogger(__name__)

_TABLES = """
CREATE TABLE IF NOT EXISTS meta_spend (
    id {serial},
    day TEXT NOT NULL,              -- UTC date, YYYY-MM-DD
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,             -- text / image / voice
    model TEXT NOT NULL,
    cost_usd {float} NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS meta_spend_day ON meta_spend(day);

CREATE TABLE IF NOT EXISTS ors_requests (
    id {serial},
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

-- After-walk survey, one row per invite and role (a / b). Answers only, given with consent;
-- no location. predicted_* come from the confirmed plan, for predicted-vs-actual.
CREATE TABLE IF NOT EXISTS feedback (
    token TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL,             -- JSON
    PRIMARY KEY (token, role)
);

-- A walk recap someone chose to share: meeting point, destination, the shared route, minutes
-- walked and places passed; never a start point. Deleted RECAP_DAYS after it was made.
CREATE TABLE IF NOT EXISTS recaps (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL              -- JSON
);

CREATE TABLE IF NOT EXISTS invites (
    token TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    data TEXT NOT NULL              -- Invite JSON
);
"""
SQLITE_DDL = _TABLES.format(serial="INTEGER PRIMARY KEY AUTOINCREMENT", float="REAL")
POSTGRES_DDL = _TABLES.format(serial="BIGSERIAL PRIMARY KEY", float="DOUBLE PRECISION")

POOL_MAX = 5


class _SQLite:
    name = "sqlite"

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SQLITE_DDL)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def query(self, sql: str, params=()) -> list[dict]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def run(self, sql: str, params=()) -> None:
        with self._conn() as conn:
            conn.execute(sql, params)

    def run_many(self, sql: str, rows) -> None:
        with self._conn() as conn:
            conn.executemany(sql, rows)


class _Postgres:
    name = "postgres"

    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self._errors = (psycopg.OperationalError, psycopg.InterfaceError)
        self.pool = ConnectionPool(
            url, min_size=0, max_size=POOL_MAX, open=True, timeout=20,
            kwargs={"row_factory": dict_row, "prepare_threshold": None, "connect_timeout": 15},
            check=ConnectionPool.check_connection,  # drop connections Neon closed while idle
        )
        self._do(lambda cur: [cur.execute(s) for s in POSTGRES_DDL.split(";") if s.strip()])

    def _do(self, work):
        for attempt in range(2):
            try:
                with self.pool.connection() as conn, conn.cursor() as cur:
                    return work(cur)
            except self._errors as e:
                if attempt:
                    raise
                log.warning("postgres connection error (%s); retrying once", type(e).__name__)

    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("?", "%s")

    def query(self, sql: str, params=()) -> list[dict]:
        def work(cur):
            cur.execute(self._sql(sql), params)
            return list(cur.fetchall())
        return self._do(work)

    def run(self, sql: str, params=()) -> None:
        self._do(lambda cur: cur.execute(self._sql(sql), params))

    def run_many(self, sql: str, rows) -> None:
        rows = list(rows)
        self._do(lambda cur: cur.executemany(self._sql(sql), rows))


_backends: dict[str, object] = {}
_lock = threading.Lock()


def db(path: Path | None = None):
    """The storage backend: Postgres if DATABASE_URL is set, else SQLite at `path` (or DB_PATH)."""
    settings = get_settings()
    url = settings.database_url.get_secret_value()
    key = url or str(Path(path or settings.db_path))
    with _lock:
        if key not in _backends:
            _backends[key] = _Postgres(url) if url else _SQLite(Path(key))
        return _backends[key]


def db_region(url: str) -> str | None:
    """'aws us-east-1' from a Neon host like ep-x-pooler.us-east-1.aws.neon.tech; never the host itself."""
    from urllib.parse import urlsplit

    parts = (urlsplit(url).hostname or "").split(".")
    if len(parts) >= 5 and parts[-2:] == ["neon", "tech"]:
        return f"{parts[-3]} {parts[-4]}"
    return None


def health() -> dict:
    """Backend name, whether a trivial query works, its round trip (median of 3) and, on Neon,
    the database region (never raises)."""
    import statistics
    import time

    url = get_settings().database_url.get_secret_value()
    try:
        backend = db()
        rtts = []
        for _ in range(3):
            t = time.perf_counter()
            backend.query("SELECT 1 AS ok")
            rtts.append((time.perf_counter() - t) * 1000)
        out = {"backend": backend.name, "reachable": True, "round_trip_ms": round(statistics.median(rtts), 1)}
    except Exception as e:  # report, don't crash /health
        out = {"backend": "postgres" if url else "sqlite", "reachable": False, "error": type(e).__name__}
    if url:
        out["region"] = db_region(url)
    return out


def save_invite(invite, path: Path | None = None) -> None:
    from datetime import datetime, timezone

    db(path).run(
        "INSERT INTO invites (token, status, created_at, expires_at, data) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (token) DO UPDATE SET status = excluded.status, expires_at = excluded.expires_at, "
        "data = excluded.data",
        (invite.token, invite.status, datetime.now(timezone.utc).isoformat(), invite.expires_at.isoformat(),
         invite.model_dump_json()),
    )


def load_invite(token: str, path: Path | None = None):
    from app.models.schemas import Invite

    rows = db(path).query("SELECT data FROM invites WHERE token = ?", (token,))
    return Invite.model_validate_json(rows[0]["data"]) if rows else None


def save_invite_extra(token: str, public: dict, private: dict | None, path: Path | None = None) -> None:
    import json

    db(path).run(
        "INSERT INTO invite_extra (token, public, private) VALUES (?, ?, ?) "
        "ON CONFLICT (token) DO UPDATE SET public = excluded.public, private = excluded.private",
        (token, json.dumps(public), None if private is None else json.dumps(private)),
    )


def load_invite_extra(token: str, path: Path | None = None) -> tuple[dict, dict | None]:
    import json

    rows = db(path).query("SELECT public, private FROM invite_extra WHERE token = ?", (token,))
    if not rows:
        return {}, None
    return json.loads(rows[0]["public"]), (json.loads(rows[0]["private"]) if rows[0]["private"] else None)


def save_feedback(token: str, role: str, data: dict, path: Path | None = None) -> None:
    import json
    from datetime import datetime, timezone

    db(path).run(
        "INSERT INTO feedback (token, role, created_at, data) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (token, role) DO UPDATE SET created_at = excluded.created_at, data = excluded.data",
        (token, role, datetime.now(timezone.utc).isoformat(), json.dumps(data)),
    )


def feedback_roles(token: str, path: Path | None = None) -> set[str]:
    return {r["role"] for r in db(path).query("SELECT role FROM feedback WHERE token = ?", (token,))}


def user_test_rows(since: str, path: Path | None = None) -> tuple[list[dict], list[dict]]:
    """Invites created since `since` (ISO time) with their public extras, and their feedback rows."""
    import json

    invites = db(path).query(
        "SELECT i.token, i.status, i.created_at, i.data, e.public FROM invites i "
        "LEFT JOIN invite_extra e ON e.token = i.token WHERE i.created_at >= ? ORDER BY i.created_at", (since,))
    for r in invites:
        r["data"], r["public"] = json.loads(r["data"]), json.loads(r["public"] or "{}")
    feedback = db(path).query(
        "SELECT f.token, f.role, f.created_at, f.data FROM feedback f JOIN invites i ON i.token = f.token "
        "WHERE i.created_at >= ? ORDER BY f.created_at", (since,))
    for r in feedback:
        r["data"] = json.loads(r["data"])
    return invites, feedback


def save_recap(recap_id: str, data: dict, path: Path | None = None) -> None:
    import json
    from datetime import datetime, timezone

    db(path).run("INSERT INTO recaps (id, created_at, data) VALUES (?, ?, ?)",
                 (recap_id, datetime.now(timezone.utc).isoformat(), json.dumps(data)))


def load_recap(recap_id: str, path: Path | None = None) -> tuple[dict, str] | None:
    import json

    rows = db(path).query("SELECT data, created_at FROM recaps WHERE id = ?", (recap_id,))
    return (json.loads(rows[0]["data"]), rows[0]["created_at"]) if rows else None


def delete_recaps_before(cutoff_iso: str, path: Path | None = None) -> None:
    db(path).run("DELETE FROM recaps WHERE created_at < ?", (cutoff_iso,))


def invites_expired_before(now_iso: str, path: Path | None = None) -> list[str]:
    """Tokens of invites past their expiry that may still hold routes (status not yet 'expired',
    or expired before routes were stripped)."""
    return [r["token"] for r in db(path).query("SELECT token FROM invites WHERE expires_at < ?", (now_iso,))]
