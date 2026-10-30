"""Solo mode: plan a walk for one person. Nothing is stored; the start point is used once."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.coverage import outside_message
from app.api.invites import LatLon
from app.core.errors import ProviderError
from app.models.schemas import WalkIntent
from app.services.solo import SoloPlan, plan_solo

router = APIRouter(prefix="/api/solo", tags=["solo"])
NYC = ZoneInfo("America/New_York")


class SoloRequest(BaseModel):
    intent: WalkIntent
    origin: LatLon
    text: str = Field(default="", max_length=500)  # what they typed: Muse Spark reads wishes from it
    pass_by_ids: list[str] = Field(default=[], max_length=3)  # "Add to my wish" from Near you: soft


class SoloResponse(SoloPlan):
    sources: dict[str, str] = {}
    demo_data: bool = False


@router.post("/plan")
def solo_plan(req: SoloRequest) -> SoloResponse:
    from app.core.config import get_settings, reasoning_override
    from app.providers import get_places, get_routing
    from app.services.nearby import resolve_pass_by
    from app.services.wishes import interpret_wishes

    reasoning_override.set(get_settings().accept_reasoning_effort)  # someone is waiting
    if msg := outside_message((req.origin.lat, req.origin.lon)):
        return SoloResponse(status="outside_area", error=msg)
    sources: dict[str, str] = {}
    try:
        places, routing = get_places(), get_routing()
    except ProviderError as e:
        return SoloResponse(status="routing_unavailable", error=e.message)
    sources["routing"], sources["places"] = routing.name, places.name
    wishes = None
    if req.text.strip():
        wishes = interpret_wishes(req.text, "")
        sources["wishes"] = wishes.source
    plan = plan_solo((req.origin.lat, req.origin.lon), req.intent, places, routing, datetime.now(NYC), wishes,
                     pass_by=resolve_pass_by(req.pass_by_ids))
    return SoloResponse(**plan.model_dump(), sources=sources,
                        demo_data=any(v in ("mock", "default") for v in sources.values()))
