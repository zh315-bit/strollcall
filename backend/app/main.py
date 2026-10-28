import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import dev, intents, invites, voice
from app.core.budget import SpendGuard
from app.core.config import ROOT_DIR, get_settings
from app.models.db import health as db_health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="StrollCall")
app.include_router(intents.router)
app.include_router(invites.router)
app.include_router(voice.router)
app.include_router(dev.router)  # answers 404 unless DEBUG=true

FRONTEND = ROOT_DIR / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/", include_in_schema=False)
def index_page() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/i/{token}", include_in_schema=False)
def invite_page(token: str) -> FileResponse:
    return FileResponse(FRONTEND / "invite.html")


@app.get("/health")
def health() -> dict:
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
            "overpass": "mock" if s.use_mocks else "live",
            "ors": keyed(bool(s.ors_api_key.get_secret_value())),
            "routing": "mock" if s.use_mocks else s.routing_provider,
            "places": "mock" if s.use_mocks else s.places_provider,
        },
        "meta_models": {"text": s.model_id, "image": s.image_model_id, "voice": s.voice_model_id},
        "meta_base_url": s.model_base_url,  # not secret; a wrong base URL shows up as 404s
        "meta_spend_today_usd": round(spent, 6),
        "daily_budget_usd": guard.daily_cap,
        "database": db_health(),
        "ors_requests_24h": ors_store.usage_24h(),
        "ors_soft_caps": {"matrix": s.ors_matrix_soft_cap, "directions": s.ors_directions_soft_cap},
    }
