"""The walking buddy's requests: what it can do now, and one request (a chip or spoken words).

The walking screen sends where the walker is and where the current leg ends; we use them once to
run the tool on our own map data and never store or log them. Only the words (and the whole
minutes left) go to Muse Spark, to pick the tool. COMPANION_ENABLED=false turns it all off.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.companion import TOOLS, Answer, Choice, WalkState, ask

router = APIRouter(prefix="/api/companion", tags=["companion"])


class Status(BaseModel):
    enabled: bool
    voice: bool  # hold to talk: Muse Voice Transcribe is configured (or mocked)


class AskRequest(BaseModel):
    text: str | None = Field(default=None, max_length=300)  # what they said (a transcript, editable)
    tool: str | None = None  # a quick-tap chip: run this tool, no model call
    args: dict = {}
    walk: WalkState


@router.get("")
def status() -> Status:
    from app.core.config import get_settings

    s = get_settings()
    return Status(enabled=s.companion_enabled,
                  voice=s.companion_enabled and (s.use_mocks or bool(s.model_api_key.get_secret_value())))


@router.post("/ask")
def companion_ask(req: AskRequest) -> Answer:
    from app.core.config import get_settings

    if not get_settings().companion_enabled:
        raise HTTPException(status_code=404, detail="the walking buddy is switched off")
    if req.tool is not None:
        if req.tool not in TOOLS:
            raise HTTPException(status_code=422, detail="unknown tool")
        args = {k: v for k, v in req.args.items() if k in ("kind", "place_id", "minutes", "avoid")}
        return ask(None, Choice(tool=req.tool, **args), req.walk)
    if not (req.text or "").strip():
        raise HTTPException(status_code=422, detail="say or tap something")
    return ask(req.text.strip(), None, req.walk)
