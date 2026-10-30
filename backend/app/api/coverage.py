"""The area the walking map covers, so pages can show it and say when a start point is outside."""

from fastapi import APIRouter, Response

router = APIRouter(prefix="/api", tags=["coverage"])

AREA_LABEL = "Manhattan, northern Brooklyn, Long Island City, and Jersey City, Hoboken and their neighbors in New Jersey"


def outside_message(*points: tuple[float, float]) -> str | None:
    """A plain message when a start point is off our walking map and nothing else can route it
    (no ORS key), else None. The pages check this first; this keeps the API as clear."""
    from app.core.config import get_settings
    from app.core.errors import ProviderError
    from app.providers import get_routing
    from app.providers.local_routing import OutsideCoverage

    if get_settings().ors_api_key.get_secret_value():
        return None  # ORS can route beyond the local map
    try:
        routing = get_routing()
    except ProviderError:
        return None
    if not hasattr(routing, "graph"):
        return None
    for p in points:
        try:
            routing.graph.snap(p)
        except OutsideCoverage:
            return (f"That start point is outside the area StrollCall can plan walks in ({AREA_LABEL}), or too "
                    "far from a street we have mapped. Pick a start point inside the covered area.")
    return None


@router.get("/coverage")
def coverage(response: Response) -> dict:
    from app.core.errors import ProviderError
    from app.providers import get_routing

    try:
        routing = get_routing()
    except ProviderError:
        return {"bbox": None, "label": None}
    if not hasattr(routing, "graph"):
        return {"bbox": None, "label": None}  # mock or ORS: no fixed area
    response.headers["Cache-Control"] = "max-age=3600"
    return {**routing.graph.coverage(), "label": AREA_LABEL}
