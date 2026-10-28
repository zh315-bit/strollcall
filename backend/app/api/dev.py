"""Developer-only endpoints, enabled with DEBUG=true. Not part of the product flow."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.models.schemas import WalkIntent
from app.providers import get_ors, get_overpass
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


class DevPlanResponse(PlanResult):
    source: str  # live / mock (fixtures)


@router.post("/plan")
def dev_plan(req: DevPlanRequest) -> DevPlanResponse:
    settings = get_settings()
    if not settings.debug:
        raise HTTPException(status_code=404)
    try:
        overpass, ors = get_overpass(), get_ors()
    except Exception as e:  # e.g. ORS_API_KEY missing
        return DevPlanResponse(status="routing_unavailable", error=str(e), source="live")
    result = plan_walk(
        (req.a.lat, req.a.lon),
        (req.b.lat, req.b.lon),
        req.intent,
        overpass,
        ors,
        req.depart_at or datetime.now(NYC),
    )
    return DevPlanResponse(**result.model_dump(), source="mock" if settings.use_mocks else "live")
