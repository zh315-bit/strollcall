"""In-app walking guidance: re-plan a leg from where the walker is now.

The browser follows the route and decides when someone is off it; it sends only the current
position and the target (a meetup point or destination, which are public places). Nothing is
stored and positions are never logged. Local walking graph only: no external routing call.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.invites import LatLon
from app.models.schemas import RouteLeg

router = APIRouter(prefix="/api/walk", tags=["walk"])


class RouteRequest(BaseModel):
    origin: LatLon  # current position, used once
    target: LatLon


@router.post("/route")
def route(req: RouteRequest) -> RouteLeg:
    from app.core.errors import ProviderError
    from app.providers import get_routing
    from app.providers.local_routing import OutsideCoverage

    routing = get_routing()
    if not hasattr(routing, "graph"):
        raise HTTPException(status_code=503, detail="re-planning needs the local walking map")
    origin, target = (req.origin.lat, req.origin.lon), (req.target.lat, req.target.lon)
    try:
        routing.graph.snap(origin), routing.graph.snap(target)  # inside the covered area only
        return routing.walk(origin, target)
    except OutsideCoverage:
        raise HTTPException(status_code=422, detail="you're outside the area we can route in") from None
    except ProviderError as e:
        raise HTTPException(status_code=503, detail=e.message) from e
