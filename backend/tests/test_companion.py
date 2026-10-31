"""The walking buddy on a synthetic street grid, offline: chips run tools without the model, spoken
requests go through the (mock) model or the rules, route changes come back as legs to follow."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import ProviderError
from app.main import app
from app.models.schemas import Place
from app.providers.local_routing import LocalRouting
from app.services.companion import choose_by_rules

from .test_local_providers import LAT0, LON0, STEP, grid_graph

client = TestClient(app)
SAT_15 = datetime(2026, 10, 31, 15)


@pytest.fixture
def grid(tmp_path, monkeypatch):
    g, dlon = grid_graph(tmp_path / "g.npz")

    def at(i, j):
        return LAT0 + i * STEP, LON0 + j * dlon

    def place(pid, name, ij, category, hours="24/7"):
        return Place(id=pid, name=name, lat=at(*ij)[0], lon=at(*ij)[1], category=category, opening_hours=hours)

    shops = [place("node/1", "Corner Cafe", (2, 2), "cafe"), place("node/2", "Mid Cafe", (2, 1), "cafe"),
             place("node/3", "End Cafe", (4, 4), "cafe"), place("node/4", "Shut Cafe", (1, 1), "cafe", "Mo 08:00-09:00")]

    class Places:
        name = "snapshot"

        def destination_candidates(self, lat, lon, r, types=None):
            from app.core.geo import haversine_m

            return [p for p in shops if (types is None or p.category in types) and haversine_m(lat, lon, p.lat, p.lon) <= r]

    routing = LocalRouting(g)
    monkeypatch.setattr("app.providers.get_routing", lambda: routing)
    monkeypatch.setattr("app.providers.get_places", lambda: Places())
    start, end = at(0, 0), at(4, 4)
    walk = {"lat": start[0], "lon": start[1], "target_lat": end[0], "target_lon": end[1], "target_name": "End Cafe",
            "target_category": "cafe", "minutes_left": routing.walk(start, end).duration_min}
    return {"walk": walk, "at": at, "routing": routing}


def chip(walk, tool, **args):
    resp = client.post("/api/companion/ask", json={"tool": tool, "args": args, "walk": walk})
    assert resp.status_code == 200, resp.text
    return resp.json()


def text_of(answer):
    return "".join(p if isinstance(p, str) else p["b"] for p in answer["parts"])


def test_add_stop_routes_through_an_open_cafe_and_says_what_it_costs(grid):
    a = chip(grid["walk"], "add_stop", kind="cafe")
    assert a["tool"] == "add_stop" and a["source"] == "chip" and a["replace"] == "current"
    leg = a["legs"][0]
    assert leg["geometry"][0] == [grid["walk"]["lat"], grid["walk"]["lon"]]
    assert leg["geometry"][-1] == [grid["walk"]["target_lat"], grid["walk"]["target_lon"]]
    stop = leg["stops"][0]
    assert stop["name"] in ("Corner Cafe", "Mid Cafe") and stop["stop"] == 1  # never the closed one
    assert any(p.get("stop") == 1 for p in leg["pois"])
    assert text_of(a).startswith(f"Added a coffee stop: {stop['name']}, open when you get there, per OpenStreetMap.")
    assert "more" in text_of(a) or "no extra time" in text_of(a)


def test_add_stop_for_a_place_from_whats_nearby(grid):
    a = chip(grid["walk"], "add_stop", place_id="node/1")
    assert a["legs"][0]["stops"][0]["name"] == "Corner Cafe"
    assert chip(grid["walk"], "add_stop", place_id="node/999")["legs"] is None


def test_add_stop_without_a_match_keeps_the_route(grid):
    a = chip(grid["walk"], "add_stop", kind="bakery")
    assert a["legs"] is None and "couldn't find an open bakery" in text_of(a)
    assert {c["tool"] for c in a["chips"]} == {"set_time_left", "whats_nearby"}


def test_set_time_left_that_already_fits_changes_nothing(grid):
    a = chip(grid["walk"], "set_time_left", minutes=30)
    assert a["legs"] is None and text_of(a).startswith("You're fine")


def test_set_time_left_picks_a_nearer_end_through_the_planner(grid):
    a = chip(grid["walk"], "set_time_left", minutes=5)
    assert a["replace"] == "rest"
    leg = a["legs"][0]
    assert leg["name"] == "Mid Cafe" and leg["minutes"] <= 5
    assert text_of(a).startswith("New end: Mid Cafe (cafe")


def test_set_time_left_on_a_loop_heads_back_to_the_start(grid):
    start = grid["at"](0, 1)
    walk = {**grid["walk"], "start_lat": start[0], "start_lon": start[1], "target_kind": "turnaround"}
    a = chip(walk, "set_time_left", minutes=5)
    leg = a["legs"][0]
    assert leg["name"] == "your start" and leg["target"] == list(start) and a["replace"] == "rest"


def test_set_time_left_never_moves_a_friends_meeting_point(grid):
    a = chip({**grid["walk"], "fixed_target": True}, "set_time_left", minutes=5)
    assert a["legs"] is None and "kept the plan" in text_of(a)


def test_reroute_avoid_without_flagged_streets_says_so(grid):
    a = chip(grid["walk"], "reroute_avoid", avoid="stairs")
    assert a["legs"] is None and "doesn't mark stairs" in text_of(a)


def test_reroute_avoid_takes_another_way_where_the_map_marks_it(grid):
    from app.providers.local_routing import AVOID_FLAGS

    graph = grid["routing"].graph
    before = grid["routing"].walk((grid["walk"]["lat"], grid["walk"]["lon"]), (grid["walk"]["target_lat"], grid["walk"]["target_lon"]))
    graph.edge_flags = graph.edge_flags.copy()
    graph.edge_flags[:len(graph.edge_flags) // 2] |= AVOID_FLAGS["busy_avenues"]  # half the streets are "busy"
    a = chip(grid["walk"], "reroute_avoid", avoid="busy_avenues")
    assert a["legs"][0]["avoid"] == ["busy_avenues"] and a["legs"][0]["geometry"] != [list(p) for p in before.geometry]
    assert text_of(a).startswith("New way avoiding busy avenues")


def test_identify_landmark_only_from_map_data(grid):
    a = chip(grid["walk"], "identify_landmark")
    assert a["legs"] is None and "can't find a named landmark" in text_of(a)


def test_spoken_request_goes_through_the_model(grid):
    resp = client.post("/api/companion/ask", json={"text": "I could use a coffee", "walk": grid["walk"]})
    a = resp.json()
    assert a["source"] == "mock" and a["tool"] == "add_stop" and a["heard"] == "I could use a coffee"


def test_spoken_request_falls_back_to_rules_without_the_model(grid, monkeypatch):
    def broken(kind="text"):
        raise ProviderError("model_unavailable", "no key")

    monkeypatch.setattr("app.providers.get_meta", broken)
    a = client.post("/api/companion/ask", json={"text": "I only have 5 minutes", "walk": grid["walk"]}).json()
    assert a["source"] == "rules" and a["tool"] == "set_time_left" and a["legs"][0]["name"] == "Mid Cafe"


def test_rules():
    assert choose_by_rules("grab a latte on the way").kind == "cafe"
    assert choose_by_rules("I have 10 min").minutes == 10
    assert choose_by_rules("what's that building?").tool == "identify_landmark"
    assert choose_by_rules("anything nearby?").tool == "whats_nearby"
    assert choose_by_rules("can we avoid the stairs").avoid == "stairs"
    assert choose_by_rules("is it safe here").tool == "none"


def test_feature_flag_hides_the_buddy(grid, monkeypatch):
    assert client.get("/api/companion").json() == {"enabled": True, "voice": True}
    monkeypatch.setenv("COMPANION_ENABLED", "false")
    get_settings.cache_clear()
    assert client.get("/api/companion").json()["enabled"] is False
    assert client.post("/api/companion/ask", json={"tool": "whats_nearby", "walk": grid["walk"]}).status_code == 404


def test_unknown_tool_is_refused(grid):
    assert client.post("/api/companion/ask", json={"tool": "delete_walk", "walk": grid["walk"]}).status_code == 422


def test_identify_landmark_prefers_the_kind_they_name(grid):
    at = grid["at"]

    class Pois:
        pois = [{"id": "n/1", "name": "Corner Fountain", "category": "fountain", "pts": [list(at(0, 0))]},
                {"id": "n/2", "name": "Garibaldi", "category": "artwork", "pts": [list(at(0, 1))]}]

    grid["routing"].pois = Pois()
    from app.services import companion
    from app.services.companion import WalkState

    s = WalkState(**grid["walk"])
    assert "Corner Fountain" in text_of(companion.identify_landmark(s, "what's that?").model_dump())
    assert "Garibaldi" in text_of(companion.identify_landmark(s, "what's that statue?").model_dump())
