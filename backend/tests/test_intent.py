import pytest

from app.providers.meta import MetaInvalidJSON
from app.services import intent as intent_service
from app.services.intent import parse_intent


class FakeMeta:
    name = "meta"

    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def structured_json(self, system, user, schema, name="result"):
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def use_meta(monkeypatch):
    def install(fake):
        monkeypatch.setattr("app.providers.get_meta", lambda *a, **k: fake)

    return install


def test_parse_with_mock_provider():
    parsed = parse_intent("25 minutes, quiet streets, coffee at the end")
    assert parsed.source == "mock"
    assert parsed.intent.duration_min == 25
    assert parsed.intent.endpoint_type == "cafe"


def test_valid_model_output(use_meta):
    use_meta(FakeMeta({
        "duration_min": 30, "vibes": ["Quiet", "quiet ", "green"], "endpoint_type": "park",
        "avoid": [], "hard_constraints": [], "inferred_fields": ["vibes", "bogus"],
    }))
    parsed = parse_intent("half an hour, somewhere green")
    assert parsed.source == "meta"
    assert parsed.intent.duration_min == 30
    assert parsed.intent.vibes == ["quiet", "green"]
    assert parsed.inferred_fields == ["vibes"]


def test_bad_json_falls_back_to_default(use_meta, caplog):
    use_meta(FakeMeta(error=MetaInvalidJSON("Muse Spark returned invalid JSON")))
    parsed = parse_intent("25 minutes, quiet streets")
    assert parsed.source == "default"
    assert parsed.intent.duration_min == intent_service.DEFAULT_DURATION_MIN
    assert parsed.note == "model_unavailable"
    assert "fell back to default" in caplog.text


def test_schema_violation_falls_back_to_default(use_meta, caplog):
    use_meta(FakeMeta({"duration_min": 5, "vibes": "not a list"}))
    parsed = parse_intent("5 minutes")
    assert parsed.source == "default"
    assert parsed.note == "invalid_model_output"
    assert "duration_min" in caplog.text


def test_empty_text_skips_the_model(use_meta):
    use_meta(FakeMeta(error=AssertionError("should not be called")))
    assert parse_intent("   ").source == "default"


def test_parse_endpoint_runs_at_minimal_effort_with_a_tight_output_cap(monkeypatch):
    """Reading A's wish is on the critical path (2026-10-30: 6.4 s at low effort, about 3 s at minimal)."""
    from fastapi.testclient import TestClient

    from app.core.config import get_settings, output_cap_override, reasoning_override
    from app.main import app
    from app.providers.mock import MockMeta

    seen = {}

    class Recording(MockMeta):
        name = "meta"

        def structured_json(self, system, user, schema, name="result"):
            seen.update(effort=reasoning_override.get(), cap=output_cap_override.get())
            return super().structured_json(system, user, schema, name)

    monkeypatch.setattr("app.providers.get_meta", lambda kind="text": Recording())
    assert TestClient(app).post("/api/intents/parse", json={"text": "25 minutes, coffee"}).status_code == 200
    assert seen == {"effort": get_settings().accept_reasoning_effort, "cap": get_settings().parse_max_output_tokens}
    assert seen["effort"] == "minimal" and seen["cap"] < get_settings().meta_max_output_tokens
    assert output_cap_override.get() is None  # reset after the call
