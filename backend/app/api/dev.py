"""Developer-only endpoints, enabled with DEBUG=true. Not part of the product flow."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import ProviderError
from app.models.schemas import WalkIntent
from app.providers import get_places, get_routing
from app.services.planner import PlanResult, plan_walk

router = APIRouter(prefix="/api/dev", tags=["dev"])
NYC = ZoneInfo("America/New_York")


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class DevPlanRequest(BaseModel):
    a: LatLon
    b: LatLon
    intent: WalkIntent
    depart_at: datetime | None = None  # default: now in New York
    debug: bool = False  # include the equal-time contour (local routing only)


class DevPlanResponse(PlanResult):
    source: str  # mock (fixtures) or live:<routing>+<places>, e.g. live:local+snapshot


@router.post("/plan")
def dev_plan(req: DevPlanRequest) -> DevPlanResponse:
    settings = get_settings()
    if not settings.debug:
        raise HTTPException(status_code=404)
    try:
        places, routing = get_places(), get_routing()
    except ProviderError as e:  # e.g. local data not built
        return DevPlanResponse(status=e.code if e.code == "places_unavailable" else "routing_unavailable",
                               error=e.message, source="live")
    result = plan_walk(
        (req.a.lat, req.a.lon),
        (req.b.lat, req.b.lon),
        req.intent,
        places,
        routing,
        req.depart_at or datetime.now(NYC),
        debug=req.debug,
    )
    source = "mock" if settings.use_mocks else f"live:{routing.name}+{places.name}"
    return DevPlanResponse(**result.model_dump(), source=source)


IP_INFO_SOURCES = ("https://ipinfo.io/json", "https://ipapi.co/json/")


def _egress() -> list[dict]:
    """The server's public egress IP and its geolocation, from public IP-info services."""
    import httpx

    out = []
    for url in IP_INFO_SOURCES:
        try:
            d = httpx.get(url, timeout=10, headers={"User-Agent": "StrollCall diagnostics"}).json()
            out.append({"source": url, "ip": d.get("ip"), "city": d.get("city"), "region": d.get("region"),
                        "country": d.get("country") or d.get("country_code"), "org": d.get("org"),
                        "timezone": d.get("timezone")})
        except Exception as e:
            out.append({"source": url, "error": type(e).__name__})
    return out


def _meta_calls(n: int = 3) -> list[dict]:
    """n x GET /v1/models and n x a tiny muse-spark-1.3 chat completion, with request IDs."""
    from datetime import datetime, timezone

    import openai
    from openai import OpenAI

    from app.core.budget import SpendGuard, text_cost
    from app.providers.meta import request_id

    s = get_settings()
    client = OpenAI(base_url=s.model_base_url, api_key=s.model_api_key.get_secret_value(), timeout=30, max_retries=0)
    guard, rows = SpendGuard(), []

    def stamp():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    for _ in range(n):
        row = {"utc": stamp(), "endpoint": "GET /v1/models", "model": None}
        try:
            raw = client.models.with_raw_response.list()
            ids = [m.id for m in raw.parse()]
            row.update({"status": raw.http_response.status_code, "request_id": request_id(raw.headers),
                        "models_listed": len(ids), "lists_text_model": s.model_id in ids})
        except openai.APIStatusError as e:
            row.update({"status": e.status_code, "request_id": request_id(e.response.headers),
                        "error": (e.response.text or "")[:300]})
        rows.append(row)
    for _ in range(n):
        row = {"utc": stamp(), "endpoint": "POST /v1/chat/completions", "model": s.model_id}
        try:
            guard.check(text_cost(50, 64))
            raw = client.chat.completions.with_raw_response.create(
                model=s.model_id, messages=[{"role": "user", "content": "Reply with ok"}], max_completion_tokens=64)
            resp = raw.parse()
            if resp.usage:
                guard.record("text", s.model_id, text_cost(resp.usage.prompt_tokens, resp.usage.completion_tokens),
                             "support diagnostics")
            row.update({"status": raw.http_response.status_code, "request_id": request_id(raw.headers)})
        except openai.APIStatusError as e:
            body = {}
            try:
                body = (e.response.json() or {}).get("error", {})
            except ValueError:
                pass
            row.update({"status": e.status_code, "request_id": request_id(e.response.headers),
                        "error_code": body.get("code"), "error_message": body.get("message")})
        except Exception as e:
            row.update({"error": type(e).__name__})
        rows.append(row)
    return rows


@router.get("/meta_diag")
def meta_diag() -> dict:
    """Data for a Meta support ticket. Off unless META_DIAG=true; never returns the key."""
    import os
    import platform

    s = get_settings()
    if not s.meta_diag:
        raise HTTPException(status_code=404)
    return {
        "host": {"render_service": os.environ.get("RENDER_SERVICE_NAME"),
                 "render_instance": os.environ.get("RENDER_INSTANCE_ID"), "platform": platform.platform()},
        "egress": _egress(),
        "base_url": s.model_base_url,
        "calls": _meta_calls(),
    }
