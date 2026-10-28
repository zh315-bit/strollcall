from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models.db import load_invite

client = TestClient(app)


def test_health_reports_mocks_and_spend():
    body = client.get("/health").json()
    assert body["providers"] == {"meta": "mock", "overpass": "mock", "ors": "mock"}
    assert body["meta_spend_today_usd"] == 0
    assert body["daily_budget_usd"] == 15


def test_parse_intent_endpoint():
    resp = client.post("/api/intents/parse", json={"text": "25 minutes, quiet streets, coffee at the end"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"]["duration_min"] == 25
    assert body["source"] == "mock"


def test_parse_rejects_long_text():
    assert client.post("/api/intents/parse", json={"text": "x" * 501}).status_code == 422


def test_create_invite_stores_token_with_expiry():
    resp = client.post("/api/invites", json={"a_intent": {"duration_min": 25, "endpoint_type": "cafe"}})
    assert resp.status_code == 201
    body = resp.json()
    token = body["token"]
    assert len(token) >= 20 and body["invite_path"] == f"/i/{token}"
    stored = load_invite(token)
    assert stored.status == "pending"
    hours = (stored.expires_at - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 23.9 < hours <= 24
    assert client.post("/api/invites", json={"a_intent": {"duration_min": 25}}).json()["token"] != token


def test_create_invite_validates_intent():
    assert client.post("/api/invites", json={"a_intent": {"duration_min": 90}}).status_code == 422
