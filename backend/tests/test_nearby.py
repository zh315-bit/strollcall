"""'Near you' highlights and the pass-by soft preference, on the synthetic street grid."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import Place, WalkIntent
from app.providers.local_routing import LocalRouting
from app.services import nearby
from app.services.planner import Weights, pass_by_term, passed_on

from .test_local_providers import LAT0, LON0, STEP, grid_graph

client = TestClient(app)
NOON = datetime(2026, 10, 29, 12, 0, tzinfo=ZoneInfo("America/New_York"))


@pytest.fixture
def town(tmp_path, monkeypatch):
    g, dlon = grid_graph(tmp_path / "g.npz")
    at = lambda i, j: (LAT0 + i * STEP, LON0 + j * dlon)  # noqa: E731
    pois = SimpleNamespace(along=lambda geometry: [], pois=[
        {"id": "way/1", "name": "Grid Park", "category": "park", "lat": at(4, 4)[0], "lon": at(4, 4)[1],
         "pts": [list(at(3, 2)), list(at(4, 3)), list(at(3, 4))]},
        {"id": "node/2", "name": "Old Statue", "category": "historic site", "lat": at(1, 3)[0], "lon": at(1, 3)[1],
         "pts": [list(at(1, 3))]},
        {"id": "node/3", "name": "New Mural", "category": "artwork", "lat": at(0, 1)[0], "lon": at(0, 1)[1],
         "pts": [list(at(0, 1))]},
    ])
    open_cafe = Place(id="node/9", name="Day Cafe", lat=at(2, 2)[0], lon=at(2, 2)[1], category="cafe",
                      opening_hours="Mo-Su 08:00-18:00", fetched_at=datetime(2026, 10, 28))
    shut_cafe = Place(id="node/8", name="Night Cafe", lat=at(0, 0)[0], lon=at(0, 0)[1], category="cafe",
                      opening_hours="Mo-Su 20:00-23:00", fetched_at=datetime(2026, 10, 28))
    within = lambda lat, lon, r: [open_cafe, shut_cafe]  # noqa: E731
    snap = SimpleNamespace(destination=SimpleNamespace(within=within, places=[open_cafe, shut_cafe]),
                           meetup=SimpleNamespace(places=[]))
    routing = LocalRouting(g, pois=pois)
    monkeypatch.setattr("app.providers.get_routing", lambda: routing)
    monkeypatch.setattr("app.providers.get_places", lambda: SimpleNamespace(snapshot=snap, name="snapshot"))
    monkeypatch.setattr(nearby, "intro_ids", lambda: frozenset({"node/2"}))
    return at


def test_highlights_one_of_each_kind_open_now_and_sourced_first(town):
    found, _ = nearby.highlights(town(0, 0), NOON)
    by_kind = {h.kind: h for h in found}
    assert set(by_kind) == {"park", "cafe", "landmark"}
    assert by_kind["cafe"].name == "Day Cafe" and by_kind["cafe"].open_now is True  # the closed one is skipped
    assert by_kind["cafe"].hours_source == "OpenStreetMap, as of 2026-10-28"
    assert found[2].name == "Old Statue" and found[2].has_intro  # the first landmark: sourced beats nearer
    assert (by_kind["park"].lat, by_kind["park"].lon) == town(3, 2)  # the park's edge nearest the start
    assert all(1 <= h.walk_min <= 15 for h in found)


def test_nearby_endpoint_takes_the_start_by_post(town, caplog):
    r = client.post("/api/nearby", json={"origin": {"lat": town(0, 0)[0], "lon": town(0, 0)[1]}})
    assert r.status_code == 200 and len(r.json()["highlights"]) >= 2
    assert str(town(0, 0)[0]) not in caplog.text


def test_pass_by_resolves_known_ids_only_with_our_names(town):
    got = nearby.resolve_pass_by(["way/1", "made-up", "node/9", "way/1"])
    assert [p.name for p in got] == ["Grid Park", "Day Cafe"]


def test_pass_by_is_a_soft_bonus_and_named_only_when_the_route_passes(town):
    park = nearby.resolve_pass_by(["way/1"])
    assert pass_by_term([(town(0, 0), town(3, 2))], park) == 1.0
    assert pass_by_term([(town(0, 0), town(0, 1))], park) == 0.0
    assert Weights(1, 0.8, 0.6, 0.4, 0.3).pass_by > 0

    from app.providers import get_routing

    near = get_routing().walk(town(2, 2), town(4, 2))  # walks past the park's edge at (3, 2)
    far = get_routing().walk(town(0, 0), town(0, 2))
    assert passed_on([near], park) == ["Grid Park"] and passed_on([far], park) == []


def test_solo_plan_mentions_the_place_only_when_its_route_passes(town):
    from app.providers import get_places, get_routing
    from app.services.solo import plan_solo

    class Places:
        name = "snapshot"

        def destination_candidates(self, lat, lon, r, types=None):
            return [Place(id="node/9", name="Day Cafe", lat=town(4, 4)[0], lon=town(4, 4)[1], category="cafe",
                          opening_hours="24/7")]

    # From one corner to the other: every shortest route ends past (4, 3) or (3, 4), the park's edge.
    plan = plan_solo(town(0, 0), WalkIntent(duration_min=15, endpoint_type="cafe"), Places(), get_routing(), NOON,
                     pass_by=nearby.resolve_pass_by(["way/1"]))
    assert plan.status == "proposed" and "Passes Grid Park." in plan.candidates[0].rationale
    assert get_places().snapshot  # the fixture's places stay in use for resolving


def test_invite_keeps_resolved_pass_by_places_for_planning(town):
    from app.models.db import load_invite_extra

    r = client.post("/api/invites", json={"a_intent": {"duration_min": 15}, "a_origin": {"lat": town(0, 0)[0], "lon": town(0, 0)[1]},
                                         "pass_by_ids": ["way/1", "not-a-place"]})
    public, _ = load_invite_extra(r.json()["token"])
    assert [p["name"] for p in public["pass_by"]] == ["Grid Park"] and public["pass_by"][0]["pts"]


def test_five_in_turn_by_kind_and_refresh_shows_the_rest(town):
    found, more = nearby.highlights(town(0, 0), NOON, limit=5)
    assert [h.kind for h in found] == ["park", "cafe", "landmark", "landmark"]  # one park, one open cafe here
    assert not more
    again, more = nearby.highlights(town(0, 0), NOON, limit=5, exclude={h.id for h in found[:3]})
    assert [h.name for h in again] == ["New Mural"] and not more
    r = client.post("/api/nearby", json={"origin": {"lat": town(0, 0)[0], "lon": town(0, 0)[1]},
                                         "exclude_ids": [h.id for h in found]})
    assert r.json() == {"highlights": [], "more": False}
