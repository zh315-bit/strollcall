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
    )
    source = "mock" if settings.use_mocks else f"live:{routing.name}+{places.name}"
    return DevPlanResponse(**result.model_dump(), source=source)
