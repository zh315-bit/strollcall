from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.intent import ParsedIntent, parse_intent

router = APIRouter(prefix="/api/intents", tags=["intents"])


class ParseRequest(BaseModel):
    text: str = Field(max_length=500)


@router.post("/parse")
def parse(req: ParseRequest) -> ParsedIntent:
    return parse_intent(req.text)
