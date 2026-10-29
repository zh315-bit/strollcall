"""'Near you' on the New walk page: 2-3 highlights within about 15 minutes' walk of a start point.

POST, so the start point never appears in a URL; used once, not stored or logged. Local data only.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.invites import LatLon
from app.services.nearby import Highlight, highlights

router = APIRouter(prefix="/api", tags=["nearby"])


class NearbyRequest(BaseModel):
    origin: LatLon


class NearbyResponse(BaseModel):
    highlights: list[Highlight]


@router.post("/nearby")
def nearby(req: NearbyRequest) -> NearbyResponse:
    return NearbyResponse(highlights=highlights((req.origin.lat, req.origin.lon)))
