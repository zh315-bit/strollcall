from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.intent import ParsedIntent, parse_intent

router = APIRouter(prefix="/api/intents", tags=["intents"])


class ParseRequest(BaseModel):
    text: str = Field(max_length=500)


@router.post("/parse")
def parse(req: ParseRequest) -> ParsedIntent:
    from app.core.config import get_settings, reasoning_override

    reasoning_override.set(get_settings().accept_reasoning_effort)  # the person is waiting to see it
    return parse_intent(req.text)
