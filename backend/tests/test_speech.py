"""The walking buddy's voice (ElevenLabs): a fake client only; tests never reach the API."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services import speech

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@pytest.fixture(autouse=True)
def fresh():
    speech._reset_for_tests()
    yield
    speech._reset_for_tests()


class FakeTTS:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail
        self.text_to_speech = SimpleNamespace(convert=self.convert)

    def convert(self, voice_id, **kw):
        self.calls.append((voice_id, kw))
        if self.fail:
            raise RuntimeError("boom")
        return iter([b"ID3", b"audio"])


def test_speaks_in_the_buddy_voice_and_caches_repeats():
    fake, s = FakeTTS(), get_settings()
    assert speech.speak("  Turn left on\nBleecker Street. ", client=fake) == b"ID3audio"
    voice_id, kw = fake.calls[0]
    assert voice_id == s.elevenlabs_voice_id and kw["model_id"] == "eleven_flash_v2_5"
    assert kw["text"] == "Turn left on Bleecker Street."  # only the line, tidied; no position
    assert speech.speak("Turn left on Bleecker Street.", client=fake) == b"ID3audio"
    assert len(fake.calls) == 1


def test_failures_and_the_daily_cap_fall_back(monkeypatch):
    with pytest.raises(speech.SpeechUnavailable):
        speech.speak("Hello", client=FakeTTS(fail=True))
    monkeypatch.setenv("ELEVENLABS_DAILY_CHAR_CAP", "10")
    get_settings.cache_clear()
    speech._reset_for_tests()
    speech.speak("Hi there", client=FakeTTS())
    with pytest.raises(speech.SpeechUnavailable, match="daily"):
        speech.speak("Another line", client=FakeTTS())


def test_no_key_means_the_phone_voice():
    from app.main import app

    c = TestClient(app)
    r = c.post("/api/voice/speak", json={"text": "Voice prompts on."})
    assert r.status_code == 503 and r.json()["detail"] == "no ElevenLabs key"
    assert c.get("/health").json()["buddy_voice"]["provider"] == "device"
    assert c.post("/api/voice/speak", json={"text": "x" * (speech.MAX_CHARS + 1)}).status_code == 422


def test_endpoint_returns_mp3(monkeypatch):
    from app.main import app

    monkeypatch.setattr(speech, "speak", lambda text: b"ID3audio")
    r = TestClient(app).post("/api/voice/speak", json={"text": "You made it!"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3audio"


def test_walking_screen_uses_the_voice_and_falls_back_to_the_phone():
    walk = (FRONTEND / "js" / "walk.js").read_text()
    assert '"/api/voice/speak"' in walk
    assert "sayOnPhone(text)" in walk and "speechSynthesis.speak" in walk
    assert "unlockAudio()" in walk  # played inside the tap, for iPhone
