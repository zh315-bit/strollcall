"""POST /api/options/understand: "Something else" typed under Pass by, Avoid or Stops on the way,
as what the planner can honor (services/custom_options.py). The start, when sent, only picks the
nearest of several places with the typed name; it is not sent to the model or stored."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.invites import LatLon
from app.services.custom_options import MAX_TEXT, Field as OptionField, Understood, understand

router = APIRouter(prefix="/api/options", tags=["options"])


class UnderstandRequest(BaseModel):
    field: OptionField
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    origin: LatLon | None = None


@router.post("/understand")
def understand_option(req: UnderstandRequest) -> Understood:
    return understand(req.field, req.text, (req.origin.lat, req.origin.lon) if req.origin else None)
