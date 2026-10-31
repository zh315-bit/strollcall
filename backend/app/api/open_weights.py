import hmac

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services import open_weights

router = APIRouter(prefix="/api/open-weights", tags=["open-weights"])


class WindowRequest(BaseModel):
    minutes: float = Field(ge=0, le=open_weights.MAX_WINDOW_MIN)


@router.post("/window")
def set_window(req: WindowRequest, authorization: str = Header(default="")) -> dict:
    """Called by scripts/glimmer_warm.py once the endpoint answers. Authorized with the Modal
    proxy token this server already holds; answers 404 when open weights are not configured."""
    key = get_settings().open_weights_api_key.get_secret_value()
    if not key:
        raise HTTPException(404)
    if not hmac.compare_digest(authorization.encode(), f"Bearer {key}".encode()):
        raise HTTPException(403, "wrong token")
    until = open_weights.set_window(req.minutes)
    return {"open": until is not None, "until": until.isoformat() if until else None,
            "enabled": open_weights.enabled()}
