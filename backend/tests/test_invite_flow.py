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


def test_create_shows_text_card_and_demo_label(town):
    body = create(town)
    view = body["view"]
    assert view["status"] == "pending" and view["role"] == "a"
    assert view["invite_text"].startswith("Mock data")
    assert view["sources"]["invite_text"] == "mock" and view["demo_data"] is True
    assert "a_origin" not in str(body) and str(town["a"]["lat"]) not in str(body)
    # The card image is made in the background (mock placeholder here).
    again = client.get(f"/api/invites/{body['token']}").json()
    assert again["sources"]["image"] == "mock" and again["image_url"]
    assert client.get(again["image_url"]).headers["content-type"] == "image/png"


def test_full_flow_create_accept_poll_confirm(town):
    body = create(town)
    token, a_key = body["token"], body["a_key"]
    guest = client.get(f"/api/invites/{token}").json()
    assert guest["role"] == "guest" and guest["status"] == "pending"

    acc = client.post(f"/api/invites/{token}/accept", json={"b_origin": town["b"]})
    assert acc.status_code == 200
    b_key = acc.json()["b_key"]

    a_view = client.get(f"/api/invites/{token}", params={"key": a_key}).json()  # A polls
    assert a_view["status"] == "proposed", a_view
    assert a_view["candidates"] and "node/9" in a_view["places"]
    assert {"routing", "places", "negotiation", "ranking"} <= set(a_view["sources"])
    b_view = client.get(f"/api/invites/{token}", params={"key": b_key}).json()
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
    view = client.get(f"/api/invites/{body['token']}", params={"key": body["a_key"]}).json()
    assert view["status"] == "error" and view["error"] == "no_feasible_plan"
    assert view["failure"]["suggestion"]


def test_unknown_invite_404():
    assert client.get("/api/invites/nope").status_code == 404


def test_voice_transcribe_mock_and_rejects_non_wav():
    ok = client.post("/api/voice/transcribe", files={"audio": ("a.wav", wav_bytes(), "audio/wav")})
    assert ok.status_code == 200 and ok.json()["source"] == "mock" and ok.json()["transcript"]
    bad = client.post("/api/voice/transcribe", files={"audio": ("a.webm", b"xxxx", "audio/webm")})
    assert bad.status_code == 400
