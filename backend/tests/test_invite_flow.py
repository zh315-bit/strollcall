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
    assert {"routing", "places", "ranking"} <= set(a_view["sources"])
    # B typed nothing: nothing to read or balance, so no parse, no negotiation and no tradeoff line.
    assert "negotiation" not in a_view["sources"] and "b_intent" not in a_view["sources"]
    assert a_view["tradeoff"] is None
    # Progress was kept in memory while planning and saved with the result, with stage timings.
    from app.services.invites import _live

    assert token not in _live and a_view["progress"]["step"] == "done"
    assert {"routing_search", "plan", "rank"} <= set(a_view["progress"]["timings"])
    assert not {"parse_b", "negotiate"} & set(a_view["progress"]["timings"])
    b_view = client.get(f"/api/invites/{token}", headers={"X-Invite-Key": b_key}).json()
    c_a, c_b = a_view["candidates"][0], b_view["candidates"][0]
    # Each sees their own leg in full and the other's leg trimmed at the start.
    assert len(c_a["a_leg"]["geometry"]) > len(c_b["a_leg"]["geometry"])
    assert len(c_b["b_leg"]["geometry"]) > len(c_a["b_leg"]["geometry"])
    assert c_a["a_leg"]["duration_min"] == c_b["a_leg"]["duration_min"]
    # Turn steps only for your own leg: the other's first step would sit at their start.
    assert c_a["a_leg"]["steps"] and not c_b["a_leg"]["steps"] and not c_a["b_leg"]["steps"]

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


def _expire(token):
    invite = load_invite(token)
    invite.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    save_invite(invite)


def test_expiry_deletes_routes_from_start_points_even_if_nobody_opens_the_invite(town):
    from app.services.invites import sweep_expired

    body = create(town)
    token = body["token"]
    b_key = client.post(f"/api/invites/{token}/accept", json={"b_origin": town["b"]}).json()["b_key"]
    client.post(f"/api/invites/{token}/confirm", json={"key": b_key})
    _expire(token)
    assert sweep_expired() == 1  # nobody opened it again
    stored = load_invite(token)
    assert stored.status == "expired" and load_invite_extra(token)[1] is None
    for c in stored.candidates:
        assert c.a_leg.geometry == [] and c.b_leg.geometry == [] and c.a_leg.steps == [] and c.b_leg.pois == []
        assert c.a_leg.duration_min > 0 and c.shared_leg.geometry  # times and the shared leg remain
    assert sweep_expired() == 0


class NearAndFar:
    """Fake route POIs: one 50 m after each leg's start (named after the start), one 300 m in."""

    def along(self, geometry):
        start = f"near-{geometry[0][0]:.5f},{geometry[0][1]:.5f}"
        return [{"id": start, "name": "Corner statue", "category": "artwork", "lat": 0, "lon": 0, "along_m": 50},
                {"id": "far", "name": "Big Park", "category": "park", "lat": 0, "lon": 0, "along_m": 300}]


def test_recap_has_no_start_points_and_expires_after_30_days(town, monkeypatch):
    from app.providers import get_routing
    from app.services import invites as inv

    get_routing().pois = NearAndFar()
    body = create(town)
    token, a_key = body["token"], body["a_key"]
    b_key = client.post(f"/api/invites/{token}/accept", json={"b_origin": town["b"]}).json()["b_key"]
    req = {"key": b_key, "minutes_walked": 23, "place_ids": [f"near-{town['b']['lat']:.5f},{town['b']['lon']:.5f}", "far", "made-up"]}
    assert client.post(f"/api/invites/{token}/recap", json=req).status_code == 409  # not confirmed yet
    client.post(f"/api/invites/{token}/confirm", json={"key": a_key})
    assert client.post(f"/api/invites/{token}/recap", json={**req, "key": "nope"}).status_code == 403
    r = client.post(f"/api/invites/{token}/recap", json=req)
    assert r.status_code == 201
    recap = client.get("/api/recaps/" + r.json()["recap_path"].split("/")[-1]).json()
    assert recap["minutes_walked"] == 23 and recap["image_url"] == "/static/illustrations/lively-cafe.jpg"
    assert [p["id"] for p in recap["places"]] == ["far"]  # the place near B's start is left out
    points = [tuple(p) for p in recap["shared_geometry"]] + [
        (recap["meetup"]["lat"], recap["meetup"]["lon"]), (recap["destination"]["lat"], recap["destination"]["lon"])]
    for origin in (town["a"], town["b"]):
        assert all(abs(p[0] - origin["lat"]) + abs(p[1] - origin["lon"]) > 1e-4 for p in points)
    assert recap["shared_geometry"] and "a_leg" not in str(recap) and "b_leg" not in str(recap)
    assert client.get("/r/" + r.json()["recap_path"].split("/")[-1]).status_code == 200

    monkeypatch.setattr(inv, "_now", lambda: datetime.now(timezone.utc) + timedelta(days=31))
    assert client.get("/api/recaps/" + r.json()["recap_path"].split("/")[-1]).status_code == 404


def test_start_outside_the_map_gets_a_clear_message(town):
    far = {"lat": 40.85, "lon": -73.87}  # well off the synthetic grid
    resp = client.post("/api/invites", json={"a_intent": {"duration_min": 15}, "a_origin": far})
    assert resp.status_code == 422 and "outside the area" in resp.json()["detail"]
    token = create(town)["token"]
    resp = client.post(f"/api/invites/{token}/accept", json={"b_origin": far})
    assert resp.status_code == 422 and "outside the area" in resp.json()["detail"]
    solo = client.post("/api/solo/plan", json={"intent": {"duration_min": 15}, "origin": far}).json()
    assert solo["status"] == "outside_area" and "outside the area" in solo["error"]


def test_plan_shows_before_the_ranking_then_ranking_and_reasons_follow(town, monkeypatch):
    """The plan is saved as soon as the planner is done; Muse Spark's order and reasons arrive later.
    An option confirmed in between stays confirmed."""
    from app.services import explain

    body = create(town)
    token, a_key = body["token"], body["a_key"]
    seen = {}

    def slow_rank(plan, a, b, joint, wishes=None):
        v = client.get(f"/api/invites/{token}", headers={"X-Invite-Key": a_key}).json()
        seen.update(status=v["status"], explaining=v["explaining"], reasons=v["reasons"],
                    ids=[c["id"] for c in v["candidates"]], ranking=v["sources"]["ranking"])
        client.post(f"/api/invites/{token}/confirm", json={"key": a_key, "candidate_id": plan.candidates[0].id})
        order = list(reversed(plan.candidates))
        return explain.Ranking(candidates=order, reasons={c.id: "ok" for c in order}, source="meta")

    monkeypatch.setattr(explain, "rank_candidates", slow_rank)
    client.post(f"/api/invites/{token}/accept", json={"b_origin": town["b"]})
    assert seen["status"] == "proposed" and seen["explaining"] is True
    assert seen["reasons"] == {} and seen["ranking"] == "pending" and seen["ids"]

    v = client.get(f"/api/invites/{token}", headers={"X-Invite-Key": a_key}).json()
    assert v["explaining"] is False and v["sources"]["ranking"] == "meta"
    assert [c["id"] for c in v["candidates"]] == list(reversed(seen["ids"]))
    assert set(v["reasons"]) == set(seen["ids"])
    assert v["status"] == "confirmed" and v["selected_id"] == seen["ids"][0]  # the choice made meanwhile
    if len(seen["ids"]) > 1:
        assert v["top_changed"] == {"from": seen["ids"][0], "to": seen["ids"][-1]}
    assert v["progress"]["step"] == "done"


def test_invite_line_runs_at_minimal_effort_with_a_tight_output_cap(town, monkeypatch):
    """Creating the invite waits on the invite line (2026-10-30: about 8 s live at low effort)."""
    from app.core.config import get_settings, output_cap_override, reasoning_override
    from app.providers.mock import MockMeta

    seen = {}

    class Recording(MockMeta):
        name = "meta"

        def structured_json(self, system, user, schema, name="result"):
            if name == "invite_text":
                seen.update(effort=reasoning_override.get(), cap=output_cap_override.get())
            return super().structured_json(system, user, schema, name)

    monkeypatch.setattr("app.providers.get_meta", lambda kind="text": Recording())
    create(town)
    assert seen == {"effort": "minimal", "cap": get_settings().card_max_output_tokens}
    assert output_cap_override.get() is None


def test_b_preference_parsed_while_typing_is_reused_on_accept(town, monkeypatch):
    """The page parses B's text before B taps "I'm in"; planning then reuses it, and negotiation runs."""
    from app.providers.mock import MockMeta

    calls = []

    class Counting(MockMeta):
        name = "meta"

        def structured_json(self, system, user, schema, name="result"):
            calls.append(name)
            return super().structured_json(system, user, schema, name)

    monkeypatch.setattr("app.providers.get_meta", lambda kind="text": Counting())
    body = create(town)
    text = "somewhere green, I'm bringing my dog"
    assert client.post("/api/intents/parse", json={"text": text}).status_code == 200  # while B types
    assert calls.count("walk_intent") == 1
    client.post(f"/api/invites/{body['token']}/accept", json={"b_origin": town["b"], "b_text": text})
    v = client.get(f"/api/invites/{body['token']}", headers={"X-Invite-Key": body["a_key"]}).json()
    assert calls.count("walk_intent") == 1  # not parsed again
    assert v["sources"]["b_intent"] == "meta" and "negotiation" in v["sources"]
    assert "joint_preference" in calls and v["tradeoff"]  # B said something: the two are balanced


def test_parse_cache_shares_a_running_parse_and_skips_fallbacks(monkeypatch):
    import threading

    from app.providers.mock import MockMeta
    from app.services.intent import parse_intent

    started, release, calls = threading.Event(), threading.Event(), []

    class Slow(MockMeta):
        name = "meta"

        def structured_json(self, system, user, schema, name="result"):
            calls.append(name)
            started.set()
            release.wait(5)
            return super().structured_json(system, user, schema, name)

    monkeypatch.setattr("app.providers.get_meta", lambda kind="text": Slow())
    out = []
    t = threading.Thread(target=lambda: out.append(parse_intent("25 minutes, coffee")))
    t.start()
    started.wait(5)
    waiter = threading.Thread(target=lambda: out.append(parse_intent("  25 minutes, coffee ")))
    waiter.start()
    release.set()
    t.join(5), waiter.join(5)
    assert len(calls) == 1 and len(out) == 2 and out[0] == out[1]
    # A fallback (here: the mock, labelled "mock") is not kept: the next call asks again.
    monkeypatch.setattr("app.providers.get_meta", lambda kind="text": MockMeta())
    parse_intent("an hour by the river")
    parse_intent("an hour by the river")
    from app.services import intent

    assert [f.result().source for _, f in intent._parsed.values()] == ["meta"]  # only the Meta parse is kept
