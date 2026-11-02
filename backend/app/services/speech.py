"""The walking buddy's voice: ElevenLabs text to speech for the replies and prompts the buddy reads
out on the walking screen (when the walker turned voice on).

Only the text being spoken is sent (a turn, a place name, a buddy reply), never a position. One
attempt with a short timeout; on any failure the page uses the phone's own voice instead, so a
prompt is never lost. Repeated prompts ("Voice prompts on.", the same turn for two walkers) come
from a small cache. A daily character cap (ELEVENLABS_DAILY_CHAR_CAP, all walkers) bounds spend;
past it the phone's voice reads everything until the next day (UTC).
"""

import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

from app.core.config import ROOT_DIR, Settings, forbid_live_client_in_tests, get_settings
from app.core.errors import ProviderError

log = logging.getLogger(__name__)

MAX_CHARS = 400  # a buddy reply is one or two sentences
CACHE_ITEMS = 64
OUTPUT_FORMAT = "mp3_44100_64"


class SpeechUnavailable(ProviderError):
    def __init__(self, message: str):
        super().__init__("speech_unavailable", message)


_lock = threading.Lock()
_cache: "OrderedDict[str, bytes]" = OrderedDict()
_day = {"date": "", "chars": 0}


def enabled(s: Settings | None = None) -> bool:
    s = s or get_settings()
    return bool(s.elevenlabs_api_key.get_secret_value()) and not s.use_mocks


def _client(s: Settings):
    forbid_live_client_in_tests("ElevenLabs")
    from dotenv import load_dotenv
    from elevenlabs import ElevenLabs

    load_dotenv(ROOT_DIR / ".env")  # local runs: ELEVENLABS_API_KEY from .env (on Render, the environment)
    return ElevenLabs(api_key=s.elevenlabs_api_key.get_secret_value(), timeout=s.elevenlabs_timeout_s)


def _reserve(chars: int, cap: int) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _lock:
        if _day["date"] != today:
            _day.update(date=today, chars=0)
        if _day["chars"] + chars > cap:
            raise SpeechUnavailable("daily voice limit reached")
        _day["chars"] += chars


def status(s: Settings | None = None) -> dict:
    s = s or get_settings()
    return {"provider": "elevenlabs" if enabled(s) else "device", "model": s.elevenlabs_model,
            "voice_id": s.elevenlabs_voice_id, "chars_today": _day["chars"], "daily_char_cap": s.elevenlabs_daily_char_cap}


def speak(text: str, client=None, s: Settings | None = None) -> bytes:
    """MP3 bytes of `text` in the buddy's voice. Raises SpeechUnavailable on any failure."""
    s = s or get_settings()
    text = " ".join(text.split())[:MAX_CHARS]
    if not text:
        raise SpeechUnavailable("nothing to say")
    if client is None and not enabled(s):
        raise SpeechUnavailable("no ElevenLabs key")
    key = f"{s.elevenlabs_voice_id}|{s.elevenlabs_model}|{text}"
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    _reserve(len(text), s.elevenlabs_daily_char_cap)
    started = time.monotonic()
    try:
        audio = b"".join((client or _client(s)).text_to_speech.convert(
            s.elevenlabs_voice_id, text=text, model_id=s.elevenlabs_model, output_format=OUTPUT_FORMAT))
    except Exception as e:  # noqa: BLE001 - any failure: the page falls back to the phone's voice
        log.warning("ElevenLabs speech failed (%s)", type(e).__name__)
        raise SpeechUnavailable("ElevenLabs is unavailable right now") from e
    if not audio:
        raise SpeechUnavailable("ElevenLabs returned no audio")
    log.info("ElevenLabs speech: model=%s chars=%d bytes=%d latency=%.2fs", s.elevenlabs_model, len(text),
             len(audio), time.monotonic() - started)
    with _lock:
        _cache[key] = audio
        while len(_cache) > CACHE_ITEMS:
            _cache.popitem(last=False)
    return audio


def _reset_for_tests() -> None:
    with _lock:
        _cache.clear()
        _day.update(date="", chars=0)
