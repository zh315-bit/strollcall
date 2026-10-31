"""Wish reading on Muse Glimmer (open weights, our Modal endpoint): only inside a warm window,
labelled, logged without the user's text, and falling back to the Meta API on any failure."""

import json
from types import SimpleNamespace

import openai
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services import intent, open_weights

ANSWER = ('{"duration_min": 30, "duration_strict": false, "vibes": ["Quiet"], "endpoint_type": "cafe", '
          '"avoid": [], "hard_constraints": [], "inferred_fields": []}')


class FakeCompletions:
    def __init__(self, content=ANSWER, error=None):
        self.content, self.error, self.calls = content, error, []

    def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=700, completion_tokens=60),
            choices=[SimpleNamespace(finish_reason="stop", text=self.content)])


@pytest.fixture
def glimmer(monkeypatch):
    """Glimmer switched on with a fake endpoint; the warm window decided per test."""
    from app.providers import glimmer as mod

    fake = FakeCompletions()
    real = mod.GlimmerProvider.__init__

    def init(self, settings=None, guard=None, client=None, timeout_s=None):
        real(self, settings, guard, SimpleNamespace(completions=fake), timeout_s)
    monkeypatch.setattr(mod.GlimmerProvider, "__init__", init)
    monkeypatch.setattr(open_weights, "use_glimmer", lambda: True)
    return fake


def test_glimmer_reads_the_wish_and_says_so(glimmer):
    r = intent.parse_intent("a quiet 30 minute walk to a cafe")
    assert r.source == "glimmer" and r.fallback_from is None
    assert r.intent.endpoint_type == "cafe" and r.intent.vibes == ["quiet"]
    assert r.read_by["model"] == "muse-glimmer" and r.read_by["precision"] == "BF16"
    assert r.read_by["host"] == "Modal" and r.read_by["gpu"] == "H200" and r.read_by["deployment"].startswith("ep-")
    call = glimmer.calls[0]
    assert call["prompt"].endswith("<|start|>assistant to=user<|message|>")  # reasoning off: the answer channel
    assert call["temperature"] == 0
    schema = json.loads(call["extra_body"]["json_schema"])
    assert schema["properties"]["inferred_fields"]["maxItems"] == 5  # no endless repetition
    assert "uniqueItems" not in json.dumps(schema)  # xgrammar rejects it


def test_run_log_has_the_deployment_and_no_user_text(glimmer):
    from app.models.db import db

    intent.parse_intent("my secret wish about the bakery")
    rows = db().query("SELECT model, cost_usd, detail FROM meta_spend")
    assert len(rows) == 1 and rows[0]["model"] == "muse-glimmer" and rows[0]["cost_usd"] > 0
    assert rows[0]["detail"].startswith("muse-glimmer, BF16, Modal, H200")
    assert "bakery" not in rows[0]["detail"]


@pytest.mark.parametrize("error", [openai.APITimeoutError(request=None), None])
def test_any_failure_falls_back_to_the_meta_api(glimmer, error):
    if error:
        glimmer.error = error
    else:
        glimmer.content = "not json"
    r = intent.parse_intent("a quiet 30 minute walk")
    assert r.source == "mock" and r.fallback_from == "glimmer"  # mock is the Meta provider's twin in tests


def test_outside_a_window_glimmer_is_never_called(glimmer, monkeypatch):
    monkeypatch.setattr(open_weights, "use_glimmer", lambda: False)
    r = intent.parse_intent("a quiet 30 minute walk")
    assert glimmer.calls == [] and r.source == "mock" and r.fallback_from is None


def test_glimmer_answers_are_cached_like_meta_answers(glimmer):
    intent.parse_intent("a quiet 30 minute walk")
    intent.parse_intent("a quiet 30 minute walk")
    assert len(glimmer.calls) == 1


def test_window_needs_the_endpoint_token(monkeypatch):
    from app.main import app

    client = TestClient(app)
    assert client.post("/api/open-weights/window", json={"minutes": 10}).status_code == 404  # no key: off
    monkeypatch.setenv("OPEN_WEIGHTS_API_KEY", "wk-test.ws-test")
    get_settings.cache_clear()
    assert client.post("/api/open-weights/window", json={"minutes": 10},
                       headers={"Authorization": "Bearer nope"}).status_code == 403
    r = client.post("/api/open-weights/window", json={"minutes": 10},
                    headers={"Authorization": "Bearer wk-test.ws-test"}).json()
    assert r["open"] and not r["enabled"]  # window open, but USE_MOCKS / TEXT_PROVIDER_PARSE keep it off
    assert open_weights.window_until() is not None and not open_weights.use_glimmer()
    health = client.get("/health").json()["open_weights"]
    assert health["model"] == "muse-glimmer" and health["deployment"].startswith("ep-")
    assert "wk-test" not in str(client.get("/health").json())
    r = client.post("/api/open-weights/window", json={"minutes": 0},
                    headers={"Authorization": "Bearer wk-test.ws-test"}).json()
    assert not r["open"] and open_weights.window_until() is None


def test_invite_records_which_model_read_each_wish(glimmer):
    from app.services.invites import create

    text = "a quiet 30 minute walk to a cafe"
    from app.core.config import reasoning_override

    token = reasoning_override.set(get_settings().accept_reasoning_effort)
    parsed = intent.parse_intent(text)  # what the New walk page does first
    reasoning_override.reset(token)
    invite, a_key = create(parsed.intent, (40.73, -73.99), a_text=text)
    from app.services.invites import view

    v = view(invite.token, a_key)
    assert v.read_by["a"]["source"] == "glimmer" and v.read_by["a"]["gpu"] == "H200"
    assert v.sources["a_intent"] == "glimmer"
