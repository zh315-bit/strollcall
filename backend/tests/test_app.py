from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_mocks_and_spend():
    body = client.get("/health").json()
    assert body["providers"] == {"meta": "mock", "overpass": "mock", "ors": "mock", "routing": "mock", "places": "mock"}
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


P1 = {"a": {"lat": 40.73164, "lon": -74.00099}, "b": {"lat": 40.72985, "lon": -73.99139},
      "intent": {"duration_min": 25, "endpoint_type": "cafe", "vibes": ["quiet"]},
      "depart_at": "2026-10-31T15:00:00-04:00"}


def test_dev_plan_hidden_without_debug():
    assert client.post("/api/dev/plan", json=P1).status_code == 404


def test_dev_plan_with_fixtures(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("DEBUG", "true")
    get_settings.cache_clear()
    body = client.post("/api/dev/plan", json=P1).json()
    assert body["status"] == "proposed" and body["source"] == "mock"
    assert len(body["candidates"]) == 3


def test_pages_are_served():
    assert "StrollCall" in client.get("/").text
    page = client.get("/i/sometoken")
    assert page.status_code == 200 and "invite" in page.text.lower()
    assert client.get("/static/js/common.js").status_code == 200


def test_health_reports_the_database():
    assert client.get("/health").json()["database"] == {"backend": "sqlite", "reachable": True}


def test_same_sql_runs_on_sqlite_with_upserts(tmp_path):
    from datetime import datetime, timezone

    from app.models.db import load_invite, save_invite
    from app.models.schemas import Invite, WalkIntent

    inv = Invite(token="t1", status="pending", expires_at=datetime.now(timezone.utc), invite_text="x",
                 a_intent=WalkIntent(duration_min=25))
    save_invite(inv)
    save_invite(inv.model_copy(update={"status": "proposed"}))  # upsert, not a duplicate-key error
    assert load_invite("t1").status == "proposed"


def test_meta_diag_is_off_by_default():
    assert client.get("/api/dev/meta_diag").status_code == 404
