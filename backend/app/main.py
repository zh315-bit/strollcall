import logging

from fastapi import FastAPI

from app.api import dev, intents, invites
from app.core.budget import SpendGuard
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="StrollCall")
app.include_router(intents.router)
app.include_router(invites.router)
app.include_router(dev.router)  # answers 404 unless DEBUG=true


@app.get("/health")
def health() -> dict:
    """Provider configuration and today's Meta spend. Makes no external calls."""
    s = get_settings()
    guard = SpendGuard()
    spent = guard.today_total()

    def keyed(has_key: bool) -> str:
        return "mock" if s.use_mocks else ("configured" if has_key else "missing_key")

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
        },
        "meta_models": {"text": s.model_id, "image": s.image_model_id, "voice": s.voice_model_id},
        "meta_spend_today_usd": round(spent, 6),
        "daily_budget_usd": guard.daily_cap,
    }
