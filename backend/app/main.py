import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import coverage, dev, intents, invites, nearby, open_weights, solo, voice, walk
from app.core.budget import SpendGuard
from app.core.config import ROOT_DIR, get_settings
from app.models.db import health as db_health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="StrollCall")


@app.middleware("http")
async def revalidate_pages_and_code(request, call_next):
    """Pages, scripts and styles are revalidated on every load (cheap: ETag / 304), so a fix
    reaches testers' phones right after a deploy instead of whenever their cache expires."""
    response = await call_next(request)
    path = request.url.path
    if path in ("/", "/new", "/how", "/walks", "/privacy") or path.startswith(("/i/", "/r/")) or path.endswith((".html", ".js", ".css", ".json")):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response
app.include_router(coverage.router)
app.include_router(nearby.router)
app.include_router(intents.router)
app.include_router(invites.router)
app.include_router(invites.recaps)
app.include_router(solo.router)
app.include_router(voice.router)
app.include_router(walk.router)
app.include_router(open_weights.router)
app.include_router(dev.router)  # answers 404 unless DEBUG=true

@app.on_event("startup")
def preload_map_data() -> None:
    """Load the walking graph and place snapshot in the background at startup, so the first
    planning request after a deploy or wake-up does not wait for them."""
    import threading

    def load():
        from app.providers import get_places, get_routing

        from app.services.invites import sweep_expired

        try:
            sweep_expired()  # invites that expired while the service slept
        except Exception as e:
            logging.getLogger(__name__).warning("expiry sweep skipped: %s", type(e).__name__)
        try:
            get_routing(), get_places()
        except Exception as e:  # the planner reports a missing graph itself
            logging.getLogger(__name__).warning("preload skipped: %s", type(e).__name__)

    if not get_settings().use_mocks:
        threading.Thread(target=load, daemon=True).start()


FRONTEND = ROOT_DIR / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/", include_in_schema=False)
def home_page() -> FileResponse:
    return FileResponse(FRONTEND / "home.html")


@app.get("/new", include_in_schema=False)
def new_walk_page() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/how", include_in_schema=False)
def how_page() -> FileResponse:
    return FileResponse(FRONTEND / "how.html")


@app.get("/walks", include_in_schema=False)
def walks_page() -> FileResponse:
    return FileResponse(FRONTEND / "walks.html")


@app.get("/privacy", include_in_schema=False)
def privacy_page() -> FileResponse:
    return FileResponse(FRONTEND / "privacy.html")


@app.get("/r/{recap_id}", include_in_schema=False)
def recap_page(recap_id: str) -> FileResponse:
    return FileResponse(FRONTEND / "recap.html")


@app.get("/i/{token}", include_in_schema=False)
def invite_page(token: str) -> FileResponse:
    return FileResponse(FRONTEND / "invite.html")


def key_fingerprint(key: str) -> str | None:
    """First 8 hex chars of SHA-256: enough to compare two keys, impossible to recover the key."""
    import hashlib

    return hashlib.sha256(key.encode()).hexdigest()[:8] if key else None


META_ENV_NAMES = ("MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_ID", "IMAGE_MODEL_ID", "VOICE_MODEL_ID",
                  "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID",
                  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
SECRET_HEADERS = {"authorization", "cookie", "openai-organization", "openai-project"}


def meta_check(s) -> dict:
    """One free models.list call, with the request's shape (no secrets) for comparing environments."""
    import os
    import platform
    import sys

    import httpx
    import openai
    from openai import OpenAI

    key = s.model_api_key.get_secret_value()
    out = {
        "env_vars_set": sorted(n for n in META_ENV_NAMES if os.environ.get(n) or os.environ.get(n.lower())),
        "versions": {"openai": openai.__version__, "httpx": httpx.__version__,
                     "python": sys.version.split()[0], "platform": platform.platform()},
        # The fingerprint hashes exactly the string given to the SDK, which sends "Bearer <key>" unchanged.
        "key_length": len(key),
        "key_has_surrounding_whitespace": key != key.strip(),
    }
    try:
        client = OpenAI(base_url=s.model_base_url, api_key=key, timeout=15, max_retries=0)
        raw = client.models.with_raw_response.list()
        req = raw.http_request
        sent = req.headers.get("authorization", "")
        out["request"] = {
            "method": req.method, "url": str(req.url),
            "headers": {k: ("<redacted>" if k.lower() in SECRET_HEADERS else v) for k, v in sorted(req.headers.items())},
            "authorization_matches_key": sent == f"Bearer {key}",
        }
        resp = raw.http_response
        out["response"] = {"status": resp.status_code,
                           "headers": {k: v for k, v in sorted(resp.headers.items())
                                       if k.lower() not in ("set-cookie",)}}
        ids = sorted(m.id for m in raw.parse())
        out.update({"reachable": True, "models": ids, "has_text_model": s.model_id in ids})
    except Exception as e:  # report, don't crash /health
        out.update({"reachable": False, "error": type(e).__name__})
    return out


def open_weights_status(s) -> dict:
    """Wish reading on Muse Glimmer (our Modal endpoint): configuration and the warm window."""
    from app.providers.glimmer import deployment
    from app.services import open_weights

    until = open_weights.window_until() if open_weights.enabled() else None
    return {"parse_provider": s.text_provider_parse,
            "key": keyed_state(s, bool(s.open_weights_api_key.get_secret_value())),
            **deployment(s), "timeout_s": s.open_weights_timeout_s,
            "warm_window_until": until.isoformat() if until else None}


def keyed_state(s, has_key: bool) -> str:
    return "mock" if s.use_mocks else ("configured" if has_key else "missing_key")


@app.get("/health")
def health(check_meta: bool = False) -> dict:
    """Provider configuration and today's Meta spend. Makes no external calls."""
    s = get_settings()
    guard = SpendGuard()
    spent = guard.today_total()

    def keyed(has_key: bool) -> str:
        return "mock" if s.use_mocks else ("configured" if has_key else "missing_key")

    from app.providers.ors import ORSStore

    ors_store = ORSStore(s.db_path, s.ors_cache_days)
    meta = keyed(bool(s.model_api_key.get_secret_value()))
    if meta == "configured" and spent >= guard.daily_cap:
        meta = "budget_exceeded_using_mock"
    return {
        "status": "ok",
        "use_mocks": s.use_mocks,
        "providers": {
            "meta": meta,
            "text_model": "mock" if s.use_mocks else s.text_provider,  # meta / spark_open
            "overpass": "mock" if s.use_mocks else "live",
            "ors": keyed(bool(s.ors_api_key.get_secret_value())),
            "routing": "mock" if s.use_mocks else s.routing_provider,
            "places": "mock" if s.use_mocks else s.places_provider,
        },
        "meta_models": {"text": s.model_id, "image": s.image_model_id, "voice": s.voice_model_id},
        "open_weights": open_weights_status(s),
        "meta_base_url": s.model_base_url,  # not secret; a wrong base URL shows up as 404s
        "meta_key_fingerprint": key_fingerprint(s.model_api_key.get_secret_value()),
        # Diagnostics (env var names, platform, request shape) only on a DEBUG deployment.
        **({"meta_check": meta_check(s)} if check_meta and s.debug and s.model_api_key.get_secret_value() else {}),
        "meta_spend_today_usd": round(spent, 6),
        "daily_budget_usd": guard.daily_cap,
        "database": db_health(),
        "ors_requests_24h": ors_store.usage_24h(),
        "ors_soft_caps": {"matrix": s.ors_matrix_soft_cap, "directions": s.ors_directions_soft_cap},
    }
