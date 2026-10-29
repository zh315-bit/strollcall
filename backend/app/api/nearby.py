"""'Near you' on the New walk page: 2-3 highlights within about 15 minutes' walk of a start point.

POST, so the start point never appears in a URL; used once, not stored or logged. Local data only.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.invites import LatLon
from app.services.nearby import Highlight, highlights

router = APIRouter(prefix="/api", tags=["nearby"])


class NearbyRequest(BaseModel):
    origin: LatLon
    exclude_ids: list[str] = Field(default=[], max_length=200)  # already shown: the refresh arrow asks for others


class NearbyResponse(BaseModel):
    highlights: list[Highlight]
    more: bool  # another refresh can show places not shown yet


@router.post("/nearby")
def nearby(req: NearbyRequest) -> NearbyResponse:
    found, more = highlights((req.origin.lat, req.origin.lon), exclude=set(req.exclude_ids))
    return NearbyResponse(highlights=found, more=more)
