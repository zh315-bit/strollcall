"""Muse Spark Open provider, against fakes only (no key, no network)."""

from types import SimpleNamespace

import pytest

from app.core.budget import SpendGuard
from app.core.config import Settings, get_settings, reasoning_override
from app.core.errors import ProviderError
from app.providers.spark_open import SparkOpenProvider, map_effort, parse_json_object

from .test_meta_provider import FakeCompletions

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}


class Recording(FakeCompletions):
    def create(self, **kwargs):
        self.requests = getattr(self, "requests", []) + [kwargs]
        return super().create(**kwargs)


def provider(contents, **overrides):
    settings = Settings(spark_open_input_per_m=1.0, spark_open_output_per_m=3.0, **overrides)
    completions = Recording(contents)
    guard = SpendGuard(daily_cap_usd=15)
    p = SparkOpenProvider(settings=settings, guard=guard,
                          client=SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    return p, completions, guard


def test_effort_mapping_has_no_minimal():
    assert map_effort("minimal") == "low" and map_effort("high") == "high" and map_effort(None) == "low"


def test_json_schema_mode_sends_schema_and_records_spend_at_its_prices():
    p, completions, guard = provider(['{"a": 1}'])
    token = reasoning_override.set("minimal")
    try:
        assert p.structured_json("sys", "user", SCHEMA, name="intent") == {"a": 1}
    finally:
        reasoning_override.reset(token)
    req = completions.requests[0]
    assert req["model"] == "accounts/fireworks/models/muse-spark-open"
    assert req["reasoning_effort"] == "low" and req["response_format"]["type"] == "json_schema"
    assert guard.today_total() == pytest.approx((100 * 1.0 + 50 * 3.0) / 1e6)


def test_prompt_mode_puts_the_schema_in_the_prompt_and_accepts_a_fence():
    p, completions, _ = provider(['```json\n{"a": 2}\n```'], spark_open_json_mode="prompt")
    assert p.structured_json("sys", "user", SCHEMA) == {"a": 2}
    req = completions.requests[0]
    assert "response_format" not in req and '"required": ["a"]' in req["messages"][0]["content"]


def test_invalid_json_is_retried_once_then_fails():
    p, completions, _ = provider(["nope", "still nope"])
    with pytest.raises(ProviderError):
        p.structured_json("sys", "user", SCHEMA)
    assert completions.calls == 2
    assert parse_json_object('{"x": 1}') == {"x": 1}


def test_needs_prices_and_has_no_image_or_voice():
    with pytest.raises(ProviderError, match="SPARK_OPEN_INPUT_PER_M"):
        SparkOpenProvider(settings=Settings(), client=object())
    p, _, _ = provider([])
    with pytest.raises(ProviderError):
        p.generate_image("x")
    with pytest.raises(ProviderError):
        p.transcribe(b"", "audio/wav")


def test_switch_moves_only_text_jobs_and_labels_them(monkeypatch):
    from app.providers import get_meta, meta_or_mock
    from app.services.intent import parse_intent

    p, _, _ = provider(['{"duration_min": 30, "duration_strict": false, "vibes": ["quiet"], "endpoint_type": "cafe", '
                        '"avoid": [], "hard_constraints": [], "inferred_fields": []}'])
    monkeypatch.setenv("USE_MOCKS", "false")
    monkeypatch.setenv("TEXT_PROVIDER", "spark_open")
    get_settings.cache_clear()
    monkeypatch.setattr("app.providers.spark_open.SparkOpenProvider", lambda: p)

    class FakeMeta:
        name = "meta"

    monkeypatch.setattr("app.providers.meta.MetaProvider", FakeMeta)
    assert get_meta("text") is p and get_meta("voice").name == "meta" and get_meta("image").name == "meta"
    assert meta_or_mock(lambda m: m.name)[1] == "spark_open"
    parsed = parse_intent("half an hour, quiet, coffee at the end")
    assert parsed.source == "spark_open" and parsed.intent.duration_min == 30
