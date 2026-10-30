"""No Meta request ever carries a start point or any coordinate: only preference text, place
names and features, measured minutes and candidate labels. Every Muse Spark request made by the
invite flow, solo mode, voice and the ranking is recorded at the provider seam and checked."""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import WalkIntent
from app.providers.mock import MockMeta
from app.services.intent import default_negotiation

from .test_invite_flow import town  # noqa: F401  (fixture)
from .test_meta_provider import wav_bytes

client = TestClient(app)

# A decimal with 3+ places looks like a coordinate (40.736, -73.991); minutes are rounded to 1 place.
COORD_NUMBER = re.compile(r"-?\d{1,3}\.\d{3,}")
COORD_KEYS = re.compile(r'"(?:lat|lon|lng|latitude|longitude|origin|a_origin|b_origin|geometry|coordinates)"', re.I)


class RecordingMeta(MockMeta):
    """Answers like the mock but reports itself as Meta, so callers treat it as the live model."""
    name = "meta"

    def __init__(self, calls):
        super().__init__()
        self.calls = calls

    def structured_json(self, system, user, schema, name="result"):
        self.calls.append((name, system + "\n" + user))
        return super().structured_json(system, user, schema, name)

    def generate_image(self, prompt):
        self.calls.append(("image", prompt))
        return super().generate_image(prompt)

    def transcribe(self, audio_bytes, mime):
        self.calls.append(("voice", mime))  # the audio itself is the person's words, nothing else
        return super().transcribe(audio_bytes, mime)


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr("app.providers.get_meta", lambda kind="text": RecordingMeta(seen))
    return seen


def coordinate_problems(payload: str, origins) -> list[str]:
    problems = [f"coordinate-like number {m}" for m in COORD_NUMBER.findall(payload)]
    problems += [f"location key {m}" for m in COORD_KEYS.findall(payload)]
    for lat, lon in origins:
        for digits in (2, 3, 4):
            for v in (lat, lon):
                if f"{v:.{digits}f}" in payload:
                    problems.append(f"start point value {v:.{digits}f}")
    return problems


def assert_no_coordinates(calls, origins):
    assert calls, "no Meta request was made"
    for name, payload in calls:
        assert not coordinate_problems(payload, origins), (name, coordinate_problems(payload, origins))


def test_the_detector_catches_coordinates():
    assert coordinate_problems('{"lat": 40.7359, "lon": -73.9906}', [(40.7359, -73.9906)])
    assert coordinate_problems("meet near 40.736,-73.991", [])
    assert not coordinate_problems('{"a_walk_min": 9, "arrival_gap_min": 2.5, "name": "5th Ave & E 12th St"}', [])


def test_invite_flow_sends_no_coordinates_to_meta(town, calls):  # noqa: F811
    origins = [(town["a"]["lat"], town["a"]["lon"]), (town["b"]["lat"], town["b"]["lon"])]
    text = "about 15 minutes, quiet streets, coffee at the end"
    intent = client.post("/api/intents/parse", json={"text": text}).json()["intent"]
    body = client.post("/api/invites", json={"a_intent": intent, "a_origin": town["a"], "a_text": text}).json()
    client.post(f"/api/invites/{body['token']}/accept", json={"b_origin": town["b"], "b_text": "pass a park please"})
    view = client.get(f"/api/invites/{body['token']}", headers={"X-Invite-Key": body["a_key"]}).json()
    assert view["status"] == "proposed", view
    assert {"walk_intent", "invite_text", "wishes", "joint_preference"} <= {n for n, _ in calls}
    assert_no_coordinates(calls, origins)


def test_solo_and_voice_send_no_coordinates_to_meta(town, calls):  # noqa: F811
    origin = (town["a"]["lat"], town["a"]["lon"])
    resp = client.post("/api/solo/plan", json={"intent": {"duration_min": 15, "endpoint_type": "cafe"},
                                               "origin": town["a"], "text": "coffee, sit outside"})
    assert resp.status_code == 200
    resp = client.post("/api/voice/transcribe", files={"audio": ("speech.wav", wav_bytes(), "audio/wav")})
    assert resp.status_code == 200
    assert {"wishes", "voice"} <= {n for n, _ in calls}
    assert_no_coordinates(calls, [origin])


def test_ranking_on_a_real_plan_sends_no_coordinates(calls, monkeypatch):
    """Pair p1, replayed from fixtures recorded against real places: the ranking's facts."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from _common import load_cases

    from app.providers import get_ors, get_overpass
    from app.services import explain, planner

    monkeypatch.setattr(planner, "TOP_N", 3)  # the fixtures hold directions for the top 3 only
    case = next(c for c in load_cases() if c["id"] == "p1")
    plan = planner.plan_walk(case["a"], case["b"], case["intent"], get_overpass(), get_ors(), case["depart_at"])
    assert plan.status == "proposed" and len(plan.candidates) > 1
    a, b = WalkIntent(duration_min=25), WalkIntent(duration_min=25)
    explain.rank_candidates(plan, a, b, default_negotiation(a, b, "test").joint)
    assert "candidate_ranking" in {n for n, _ in calls}
    # The facts are built from the plan, which holds every leg's geometry: none of it may leak.
    assert_no_coordinates(calls, [tuple(case["a"]), tuple(case["b"])])
