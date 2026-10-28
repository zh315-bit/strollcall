"""Speech to text with Muse Voice Transcribe. The browser records and converts to WAV
(mono 16-bit PCM, 16 or 24 kHz); the transcript is shown for editing before parsing."""

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.errors import ProviderError
from app.providers import meta_or_mock
from app.providers.meta import MetaError

router = APIRouter(prefix="/api/voice", tags=["voice"])

MAX_BYTES = 2_000_000  # about 40 s at 24 kHz


class Transcript(BaseModel):
    transcript: str
    source: str  # meta / mock


@router.post("/transcribe")
async def transcribe(audio: UploadFile) -> Transcript:
    data = await audio.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="recording too long (max about 40 seconds)")
    mime = audio.content_type or "application/octet-stream"
    try:
        text, source = meta_or_mock(lambda m: m.transcribe(data, mime))
    except MetaError as e:
        status = 400 if "WAV" in e.message or "audio" in e.message else 503
        raise HTTPException(status_code=status, detail=e.message) from e
    except ProviderError as e:
        raise HTTPException(status_code=503, detail=e.message) from e
    return Transcript(transcript=text, source=source)
