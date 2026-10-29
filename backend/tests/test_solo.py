"""Solo mode on a synthetic street grid, offline."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import Place, WalkIntent
from app.providers.local_routing import LocalRouting
from app.services.solo import plan_solo
from app.services.wishes import Wish, Wishes

from .test_local_providers import LAT0, LON0, STEP, grid_graph

SAT_15 = datetime(2026, 10, 31, 15)


@pytest.fixture
def town(tmp_path):
    g, dlon = grid_graph(tmp_path / "g.npz")

    def at(i, j):
        return LAT0 + i * STEP, LON0 + j * dlon

    near = Place(id="node/1", name="Near Cafe", lat=at(0, 1)[0], lon=at(0, 1)[1], category="cafe")
    # Corner and Laptop cafe are both 7 blocks away and always open; only wifi differs.
    good = Place(id="node/2", name="Corner Cafe", lat=at(4, 3)[0], lon=at(4, 3)[1], category="cafe",
                 opening_hours="24/7")
    wifi = Place(id="node/3", name="Laptop Cafe", lat=at(3, 4)[0], lon=at(3, 4)[1], category="cafe",
                 opening_hours="24/7", tags={"internet_access": "wlan"})
    park = Place(id="way/4", name="Grid Park", lat=at(2, 4)[0], lon=at(2, 4)[1], category="park")

    class Places:
        name = "snapshot"

        def destination_candidates(self, lat, lon, r, types=None):
            return [p for p in (near, good, wifi, park) if types is None or p.category in types]

    return {"routing": LocalRouting(g), "places": Places(), "origin": at(0, 0), "block_min": STEP * 111_320 / 80}


def test_solo_finds_a_cafe_near_the_wished_length(town):
    # 8 blocks to the far corner is ~11 min; ask for 12 minutes
    plan = plan_solo(town["origin"], WalkIntent(duration_min=15, endpoint_type="cafe"), town["places"],
                     town["routing"], SAT_15)
    assert plan.status == "proposed"
    ids = [c.destination_place_id for c in plan.candidates]
    assert "node/1" not in ids  # 1 block: far too short for a 15-minute walk
    assert plan.candidates[0].leg.geometry[0] == town["origin"]
    assert "Walk about" in plan.candidates[0].rationale and "for you: cafe" in plan.candidates[0].rationale


def test_wish_changes_the_pick(town):
    intent = WalkIntent(duration_min=15, endpoint_type="cafe")
    wishes = Wishes(items=[Wish(requirement="wifi", who="A", quote="laptop")], source="meta")
    plan = plan_solo(town["origin"], intent, town["places"], town["routing"], SAT_15, wishes)
    assert plan.candidates[0].destination_place_id == "node/3"
    assert "wifi" in plan.candidates[0].rationale


def test_strict_limit_and_suggestion(town):
    plan = plan_solo(town["origin"], WalkIntent(duration_min=15, endpoint_type="bookstore"), town["places"],
                     town["routing"], SAT_15)
    assert plan.status == "no_feasible_plan"
    assert plan.failure.constraint == "no_destination_of_type"
    assert plan.failure.suggestion_type == "relaxed_preference" and plan.failure.verified


def test_solo_api_labels_sources_and_stores_nothing(town, monkeypatch):
    monkeypatch.setattr("app.providers.get_routing", lambda: town["routing"])
    monkeypatch.setattr("app.providers.get_places", lambda: town["places"])
    client = TestClient(app)
    lat, lon = town["origin"]
    body = client.post("/api/solo/plan", json={"intent": {"duration_min": 15, "endpoint_type": "cafe"},
                                               "origin": {"lat": lat, "lon": lon}, "text": "coffee, sit outside"}).json()
    assert body["status"] == "proposed" and body["sources"]["routing"] == "local"
    assert body["sources"]["wishes"] == "mock" and body["demo_data"] is True
    assert "origin" not in str(body)  # the start point is used once and not echoed back
