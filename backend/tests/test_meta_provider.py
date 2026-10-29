import io
import wave
from types import SimpleNamespace

import pytest

from app.core.budget import BudgetExceeded, SpendGuard
from app.providers.meta import MetaError, MetaInvalidJSON, MetaProvider, check_wav


class FakeCompletions:
    def __init__(self, contents, finish_reasons=None):
        self.contents = list(contents)
        self.finish_reasons = list(finish_reasons or [])
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, prompt_tokens_details=None)
        message = SimpleNamespace(content=self.contents.pop(0))
        finish = self.finish_reasons.pop(0) if self.finish_reasons else "stop"
        choice = SimpleNamespace(message=message, finish_reason=finish)
        return SimpleNamespace(choices=[choice], usage=usage)


def make_provider(contents, cap=15.0):
    completions = FakeCompletions(contents)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    guard = SpendGuard(daily_cap_usd=cap)
    return MetaProvider(client=client, guard=guard), completions, guard


def test_structured_json_records_spend():
    meta, completions, guard = make_provider(['{"a": 1}'])
    assert meta.structured_json("sys", "user", {"type": "object"}) == {"a": 1}
    assert completions.calls == 1
    assert guard.today_total() > 0


def test_one_retry_on_invalid_json():
    meta, completions, _ = make_provider(["not json", '{"a": 2}'])
    assert meta.structured_json("sys", "user", {"type": "object"}) == {"a": 2}
    assert completions.calls == 2


def test_gives_up_after_one_retry():
    meta, completions, _ = make_provider(["nope", "still nope", '{"a": 3}'])
    with pytest.raises(MetaInvalidJSON):
        meta.structured_json("sys", "user", {"type": "object"})
    assert completions.calls == 2


def test_budget_blocks_call_before_it_is_sent():
    meta, completions, guard = make_provider(['{"a": 1}'], cap=0.001)
    guard.record("text", "muse-spark-1.3", 0.001)
    with pytest.raises(BudgetExceeded):
        meta.structured_json("sys", "user", {"type": "object"})
    assert completions.calls == 0


def wav_bytes(rate=24000, seconds=1, channels=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds * channels)
    return buf.getvalue()


def test_check_wav():
    assert check_wav(wav_bytes(), "audio/wav") == 1000
    with pytest.raises(MetaError):
        check_wav(wav_bytes(), "audio/webm")
    with pytest.raises(MetaError):
        check_wav(wav_bytes(rate=44100), "audio/wav")
    with pytest.raises(MetaError):
        check_wav(wav_bytes(channels=2), "audio/wav")
    with pytest.raises(MetaError):
        check_wav(b"RIFFjunk", "audio/wav")


def test_truncated_output_is_retried_once():
    meta, completions, _ = make_provider(['{"a": ', '{"a": 1}'])
    completions.finish_reasons = ["length", "stop"]
    assert meta.structured_json("sys", "user", {"type": "object"}) == {"a": 1}
    assert completions.calls == 2


def test_intermittent_model_not_found_is_retried_once(monkeypatch):
    import httpx
    import openai

    monkeypatch.setattr("app.providers.meta.time.sleep", lambda s: None)
    req = httpx.Request("POST", "https://api.meta.ai/v1/chat/completions")
    not_found = openai.NotFoundError(
        "The requested model was not found.", response=httpx.Response(404, request=req),
        body={"code": "model_not_found", "message": "The requested model was not found."})

    class Flaky(FakeCompletions):
        def create(self, **kwargs):
            if self.calls == 0:
                self.calls += 1
                raise not_found
            return super().create(**kwargs)

    completions = Flaky(['{"a": 1}'])
    meta = MetaProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
                        guard=SpendGuard(daily_cap_usd=15))
    assert meta.structured_json("s", "u", {"type": "object"}) == {"a": 1}
    assert completions.calls == 2


def test_repeated_model_not_found_pauses_the_model(monkeypatch):
    import httpx
    import openai

    from app.core.errors import ProviderError
    from app.providers import meta as meta_mod

    monkeypatch.setattr("app.providers.meta.time.sleep", lambda s: None)
    monkeypatch.setattr(meta_mod, "_not_found_until", {})
    req = httpx.Request("POST", "https://api.meta.ai/v1/chat/completions")

    class AlwaysNotFound(FakeCompletions):
        def create(self, **kwargs):
            self.calls += 1
            raise openai.NotFoundError("not found", response=httpx.Response(404, request=req),
                                       body={"code": "model_not_found", "message": "not found"})

    completions = AlwaysNotFound([])
    meta = MetaProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
                        guard=SpendGuard(daily_cap_usd=15))
    for _ in range(2):
        with pytest.raises(ProviderError):
            meta.structured_json("s", "u", {"type": "object"})
    assert completions.calls == 2  # the second call skipped the request
    meta_mod._not_found_until.clear()  # the pause ended: requests go out again
    with pytest.raises(ProviderError):
        meta.structured_json("s", "u", {"type": "object"})
    assert completions.calls == 4


def test_health_meta_check_needs_debug():
    from fastapi.testclient import TestClient

    from app.main import app

    assert "meta_check" not in TestClient(app).get("/health", params={"check_meta": 1}).json()
