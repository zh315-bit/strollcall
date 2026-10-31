"""When wish reading may use Muse Glimmer: only inside a warm window.

The Modal endpoint scales to zero after 2 idle minutes and takes about 3 minutes to start, so a
call to a cold endpoint would bill a GPU start and still fall back to the Meta API. The owner
opens a window with scripts/glimmer_warm.py, which warms the endpoint, keeps it warm and tells
this server until when (POST /api/open-weights/window, authorized with the same Modal proxy
token the server holds). Outside a window, wishes go straight to the Meta API.
The window is kept in the database so every worker sees it.
"""

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.models.db import db

MAX_WINDOW_MIN = 90


def _now() -> datetime:
    return datetime.now(timezone.utc)


def window_until() -> datetime | None:
    rows = db().query("SELECT until_at FROM open_weights_window WHERE id = 1")
    if not rows:
        return None
    until = datetime.fromisoformat(rows[0]["until_at"])
    return until if until > _now() else None


def set_window(minutes: float) -> datetime | None:
    """Open (or extend, or with 0 close) the warm window; returns its end, or None if closed."""
    minutes = max(0.0, min(float(minutes), MAX_WINDOW_MIN))
    until = _now() + timedelta(minutes=minutes)
    store = db()
    store.run("DELETE FROM open_weights_window WHERE id = 1")
    store.run("INSERT INTO open_weights_window (id, until_at) VALUES (1, ?)", (until.isoformat(),))
    return until if minutes > 0 else None


def enabled() -> bool:
    s = get_settings()
    return (not s.use_mocks and s.text_provider_parse == "open_weights"
            and bool(s.open_weights_api_key.get_secret_value()))


def use_glimmer() -> bool:
    """Wish reading should try Glimmer now: switched on, keyed, and inside a warm window."""
    return enabled() and window_until() is not None
