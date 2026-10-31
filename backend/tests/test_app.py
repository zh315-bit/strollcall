from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_mocks_and_spend():
    body = client.get("/health").json()
    assert body["providers"] == {"meta": "mock", "text_model": "mock", "overpass": "mock", "ors": "mock", "routing": "mock", "places": "mock"}
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
    from app.services import planner

    monkeypatch.setattr(planner, "TOP_N", 3)  # the fixtures hold directions for the top 3 only

    monkeypatch.setenv("DEBUG", "true")
    get_settings.cache_clear()
    body = client.post("/api/dev/plan", json=P1).json()
    assert body["status"] == "proposed" and body["source"] == "mock"
    assert len(body["candidates"]) == 3


def test_pages_are_served():
    home = client.get("/").text
    assert "StrollCall" in home and 'href="/new"' in home  # Home: "Plan my walk" leads to the New walk page
    assert "New walk" in client.get("/new").text
    page = client.get("/i/sometoken")
    assert page.status_code == 200 and "invite" in page.text.lower()
    assert client.get("/static/js/common.js").status_code == 200


def test_health_reports_the_database():
    database = client.get("/health").json()["database"]
    assert database["backend"] == "sqlite" and database["reachable"] and database["round_trip_ms"] >= 0


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


def test_meta_diag_without_key_still_reports_egress(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("META_DIAG", "true")
    monkeypatch.setattr("app.api.dev._egress", lambda: [{"source": "test", "country": "US"}])
    get_settings.cache_clear()
    body = client.get("/api/dev/meta_diag").json()
    assert body["egress"][0]["country"] == "US" and "not set" in body["calls"]


def test_db_region_names_the_cloud_region_only():
    from app.models.db import db_region

    assert db_region("postgresql://u:p@ep-cool-x-pooler.us-east-1.aws.neon.tech/db?sslmode=require") == "aws us-east-1"
    assert db_region("postgresql://u:p@localhost/db") is None


def test_pages_and_code_are_revalidated_after_a_deploy():
    for path in ("/", "/i/abc", "/static/js/walk.js", "/static/style.css"):
        assert client.get(path).headers.get("cache-control") == "no-cache", path
    assert "no-cache" not in client.get("/static/illustrations/lively-cafe.jpg").headers.get("cache-control", "")


def test_every_page_serves_with_the_nav_and_privacy_link_script():
    for path in ("/", "/i/abc", "/how", "/walks", "/privacy", "/r/abc"):
        r = client.get(path)
        assert r.status_code == 200 and "/static/js/common.js" in r.text, path


def test_postgres_ddl_splits_into_clean_statements():
    """Postgres runs the DDL split on ';' (SQLite runs it whole), so a ';' inside a comment breaks
    every database call on the deployed app. Each piece must be comments plus one CREATE."""
    from app.models.db import POSTGRES_DDL

    for piece in POSTGRES_DDL.split(";"):
        sql = "\n".join(line.split("--")[0] for line in piece.splitlines()).strip()
        assert not sql or sql.startswith("CREATE "), repr(piece[:80])
