"""Invite flow end to end through the API, offline: mock Meta, a synthetic street grid."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.db import load_invite, load_invite_extra, save_invite
from app.models.schemas import Place
from app.providers.local_routing import LocalRouting

from .test_local_providers import LAT0, LON0, STEP, grid_graph
from .test_meta_provider import wav_bytes

client = TestClient(app)


@pytest.fixture
def town(tmp_path, monkeypatch):
    """A 5x5 grid with a cafe at the top; A and B on opposite sides of row 2."""
    g, dlon = grid_graph(tmp_path / "g.npz")
    cafe = Place(id="node/9", name="Corner Cafe", lat=LAT0 + 4 * STEP, lon=LON0 + 2 * dlon, category="cafe",
                 opening_hours="24/7", tags={"amenity": "cafe", "outdoor_seating": "yes"})

    class Places:
        name = "snapshot"

        def meetup_candidates(self, lat, lon, r):
            return []

        def destination_candidates(self, lat, lon, r, types=None):
            return [cafe] if types is None or "cafe" in types else []

    routing = LocalRouting(g)
    monkeypatch.setattr("app.providers.get_routing", lambda: routing)
    monkeypatch.setattr("app.providers.get_places", lambda: Places())
    return {"a": {"lat": LAT0 + 2 * STEP, "lon": LON0}, "b": {"lat": LAT0 + 2 * STEP, "lon": LON0 + 4 * dlon}}


def create(town, text="Coffee at the end, let's sit outside"):
    resp = client.post("/api/invites", json={"a_intent": {"duration_min": 15, "endpoint_type": "cafe"},
                                             "a_origin": town["a"], "a_text": text})
    assert resp.status_code == 201
    return resp.json()


def test_create_shows_text_card_and_demo_label(town, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.invite_card.ILLUSTRATIONS_DIR", tmp_path)  # no pictures here
    body = create(town)
    view = body["view"]
    assert view["status"] == "pending" and view["role"] == "a"
    assert view["invite_text"].startswith("Mock data")
    assert view["sources"]["invite_text"] == "mock" and view["demo_data"] is True
    assert "a_origin" not in str(body) and str(town["a"]["lat"]) not in str(body)
    # No pre-generated picture for this theme here: text-only card, labelled.
    assert view["image_url"] is None and view["sources"]["image"] == "default"


def test_card_picks_the_pre_generated_illustration_by_theme(town, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.invite_card.ILLUSTRATIONS_DIR", tmp_path)
    (tmp_path / "lively-cafe.jpg").write_bytes(b"\xff\xd8")
    view = create(town)["view"]  # 15 min, ending at a cafe, no vibes
    assert view["image_url"] == "/static/illustrations/lively-cafe.jpg" and view["sources"]["image"] == "meta"


def test_themes_cover_24_pictures():
    from app.models.schemas import WalkIntent
    from app.services.invite_card import ENDINGS, SCENES, theme_for

    assert len(SCENES) * len(ENDINGS) == 24
    assert theme_for(WalkIntent(duration_min=20, vibes=["quiet"], endpoint_type="bookstore")) == ("quiet", "bookstore")
    assert theme_for(WalkIntent(duration_min=20)) == ("lively", "cafe")
    assert theme_for(WalkIntent(duration_min=20, endpoint_type="landmark")) == ("historic", "landmark")


def test_full_flow_create_accept_poll_confirm(town):
    body = create(town)
    token, a_key = body["token"], body["a_key"]
    guest = client.get(f"/api/invites/{token}").json()
    assert guest["role"] == "guest" and guest["status"] == "pending"

    acc = client.post(f"/api/invites/{token}/accept", json={"b_origin": town["b"]})
    assert acc.status_code == 200
    b_key = acc.json()["b_key"]

    a_view = client.get(f"/api/invites/{token}", headers={"X-Invite-Key": a_key}).json()  # A polls
    assert a_view["status"] == "proposed", a_view
    assert a_view["candidates"] and "node/9" in a_view["places"]
    assert {"routing", "places", "negotiation", "ranking"} <= set(a_view["sources"])
    # Progress was kept in memory while planning and saved with the result, with stage timings.
    from app.services.invites import _live

    assert token not in _live and a_view["progress"]["step"] == "done"
    assert {"routing_search", "negotiate", "plan", "rank"} <= set(a_view["progress"]["timings"])
    b_view = client.get(f"/api/invites/{token}", headers={"X-Invite-Key": b_key}).json()
    c_a, c_b = a_view["candidates"][0], b_view["candidates"][0]
    # Each sees their own leg in full and the other's leg trimmed at the start.
    assert len(c_a["a_leg"]["geometry"]) > len(c_b["a_leg"]["geometry"])
    assert len(c_b["b_leg"]["geometry"]) > len(c_a["b_leg"]["geometry"])
    assert c_a["a_leg"]["duration_min"] == c_b["a_leg"]["duration_min"]

    assert client.post(f"/api/invites/{token}/confirm", json={"key": "wrong"}).status_code == 403
    done = client.post(f"/api/invites/{token}/confirm", json={"key": b_key})
    assert done.status_code == 200
    assert done.json()["status"] == "confirmed" and done.json()["selected_id"] == c_a["id"]


def test_duplicate_accept_is_rejected(town):
    token = create(town)["token"]
    assert client.post(f"/api/invites/{token}/accept", json={"b_origin": town["b"]}).status_code == 200
    assert client.post(f"/api/invites/{token}/accept", json={"b_origin": town["b"]}).status_code == 409


def test_expired_invite_deletes_origins(town):
    token = create(town)["token"]
    invite = load_invite(token)
    invite.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    save_invite(invite)
    assert client.get(f"/api/invites/{token}").json()["status"] == "expired"
    assert load_invite_extra(token)[1] is None
    assert client.post(f"/api/invites/{token}/accept", json={"b_origin": town["b"]}).status_code == 410


def test_no_feasible_plan_is_reported(town):
    body = client.post("/api/invites", json={"a_intent": {"duration_min": 15, "endpoint_type": "bookstore"},
                                             "a_origin": town["a"]}).json()
    client.post(f"/api/invites/{body['token']}/accept", json={"b_origin": town["b"]})
    view = client.get(f"/api/invites/{body['token']}", headers={"X-Invite-Key": body["a_key"]}).json()
    assert view["status"] == "error" and view["error"] == "no_feasible_plan"
    assert view["failure"]["suggestion"]


def test_unknown_invite_404():
    assert client.get("/api/invites/nope").status_code == 404


def test_voice_transcribe_mock_and_rejects_non_wav():
    ok = client.post("/api/voice/transcribe", files={"audio": ("a.wav", wav_bytes(), "audio/wav")})
    assert ok.status_code == 200 and ok.json()["source"] == "mock" and ok.json()["transcript"]
    bad = client.post("/api/voice/transcribe", files={"audio": ("a.webm", b"xxxx", "audio/webm")})
    assert bad.status_code == 400


def test_key_in_the_url_is_ignored(town):
    body = create(town)
    view = client.get(f"/api/invites/{body['token']}", params={"key": body["a_key"]}).json()
    assert view["role"] == "guest"  # keys only count in the X-Invite-Key header (URLs are logged)


def test_events_and_after_walk_survey(town):
    from app.models.db import user_test_rows

    body = create(town)
    token, a_key = body["token"], body["a_key"]
    client.get(f"/api/invites/{token}")  # B opens the link
    b_key = client.post(f"/api/invites/{token}/accept", json={"b_origin": town["b"]}).json()["b_key"]
    answers = {"key": b_key, "would_have_gone_out": "no", "fair": "yes", "use_again": "yes", "actual_walk_min": 17}
    assert client.post(f"/api/invites/{token}/feedback", json={**answers, "consent": True}).status_code == 409
    client.post(f"/api/invites/{token}/confirm", json={"key": a_key})

    assert client.post(f"/api/invites/{token}/feedback", json=answers).status_code == 400  # no consent
    assert client.post(f"/api/invites/{token}/feedback",
                       json={**answers, "key": "nope", "consent": True}).status_code == 403
    assert client.post(f"/api/invites/{token}/feedback",
                       json={**answers, "fair": "maybe", "consent": True}).status_code == 400
    assert client.post(f"/api/invites/{token}/feedback", json={**answers, "consent": True}).status_code == 204
    assert client.get(f"/api/invites/{token}", headers={"X-Invite-Key": b_key}).json()["feedback_given"]
    assert not client.get(f"/api/invites/{token}", headers={"X-Invite-Key": a_key}).json()["feedback_given"]

    invites, feedback = user_test_rows("2000-01-01")
    row = next(r for r in invites if r["token"] == token)
    assert list(row["public"]["events"]) == ["created", "opened", "accepted", "planned", "confirmed"]
    fb = next(f for f in feedback if f["token"] == token)
    assert fb["role"] == "b" and fb["data"]["actual_walk_min"] == 17 and fb["data"]["predicted_walk_min"] > 0
    assert "lat" not in str(fb) and "origin" not in str(fb)


def test_user_test_report_has_funnel_survey_and_predicted_vs_actual(town):
    import importlib.util
    from pathlib import Path

    test_events_and_after_walk_survey(town)
    path = Path(__file__).resolve().parents[2] / "scripts" / "user_test_report.py"
    import sys
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("user_test_report", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    text = mod.report("2000-01-01", None)
    assert "| confirmed | 1 |" in text and "| Would you use it again? | 1 | 0 | 0 |" in text
    assert "median absolute difference" in text and "lat" not in text
