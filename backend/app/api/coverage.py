"""The area the walking map covers, so pages can show it and say when a start point is outside."""

from fastapi import APIRouter, Response

router = APIRouter(prefix="/api", tags=["coverage"])

AREA_LABEL = "Manhattan, northern Brooklyn and Long Island City"


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
    response.headers["Cache-Control"] = "max-age=86400"
    return {**routing.graph.coverage(), "label": AREA_LABEL}
