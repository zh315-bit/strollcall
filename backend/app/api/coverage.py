"""The area the walking map covers, so pages can show it and say when a start point is outside."""

from fastapi import APIRouter, Response

router = APIRouter(prefix="/api", tags=["coverage"])

AREA_LABEL = "Manhattan, northern Brooklyn, Long Island City, and Jersey City, Hoboken and their neighbors in New Jersey"


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
