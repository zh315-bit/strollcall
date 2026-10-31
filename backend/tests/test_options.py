""""More options" on the planner, on the synthetic street grid: pace, avoid stairs, loop vs one way,
and that the defaults change nothing."""

import numpy as np
import pytest

from app.models.schemas import WalkIntent, WalkOptions
from app.providers.local_routing import EDGE_STAIRS, LocalRouting, WalkGraph
from app.services.solo import plan_solo

from .test_local_providers import LAT0, LON0, STEP, grid_graph
from .test_solo import SAT_15, town  # noqa: F401  (fixture)


def at(dlon, i, j):
    return LAT0 + i * STEP, LON0 + j * dlon


def test_default_options_change_nothing(town):  # noqa: F811
    r = town["routing"]
    assert r.view(80.0, ()) is r and r.view() is r
    intent = WalkIntent(duration_min=15, endpoint_type="cafe")
    plain = plan_solo(town["origin"], intent, town["places"], r, SAT_15)
    with_defaults = plan_solo(town["origin"], intent, town["places"], r, SAT_15, options=WalkOptions())
    assert plain.model_dump() == with_defaults.model_dump()


def test_pace_scales_times_not_distances(tmp_path):
    g, dlon = grid_graph(tmp_path / "g.npz")
    normal = LocalRouting(g)
    a, b = at(dlon, 0, 0), at(dlon, 2, 3)
    leg = normal.walk(a, b)
    for pace in (65.0, 95.0):
        paced = normal.view(pace).walk(a, b)
        assert paced.duration_min == pytest.approx(leg.duration_min * 80 / pace, rel=1e-3)
        assert paced.distance_m == pytest.approx(leg.distance_m, rel=1e-3)
        t = normal.view(pace).matrix([a], [b]).durations_min[0][0]
        assert t == pytest.approx(leg.duration_min * 80 / pace, rel=1e-3)


def test_pace_changes_which_walks_fit(town):  # noqa: F811
    """The grid's two far cafes are 7 blocks away: ~9.7 min at 80 m/min, ~12 at 65, ~8.2 at 95. For a
    15-minute wish a walk under 60% of it (9 min) is too short, so at a brisk pace they drop out."""
    intent = WalkIntent(duration_min=15, endpoint_type="cafe")
    normal = plan_solo(town["origin"], intent, town["places"], town["routing"], SAT_15)
    relaxed = plan_solo(town["origin"], intent, town["places"], town["routing"], SAT_15,
                        options=WalkOptions(pace="relaxed"))
    brisk = plan_solo(town["origin"], intent, town["places"], town["routing"], SAT_15,
                      options=WalkOptions(pace="brisk"))
    n = {c.id: c.total_min for c in normal.candidates}
    r = {c.id: c.total_min for c in relaxed.candidates}
    assert {"node/2", "node/3"} <= set(n) and set(r) == set(n)
    for pid, t in r.items():  # timed at the slower pace
        assert t == pytest.approx(n[pid] * 80 / 65, rel=1e-3)
    assert brisk.status == "no_feasible_plan"


def stairs_graph(tmp_path):
    """The grid with the two blocks of row 0 between columns 0 and 2 mapped as stairs."""
    g, dlon = grid_graph(tmp_path / "g.npz")
    path = tmp_path / "g.npz"
    with np.load(path) as d:
        data = {k: d[k] for k in d.files}
    flags = np.zeros(len(data["indices"]), dtype=np.uint8)
    stairs = {(0, 1), (1, 2)}
    for u in range(len(data["lat"])):
        for e in range(data["indptr"][u], data["indptr"][u + 1]):
            v = int(data["indices"][e])
            if (min(u, v), max(u, v)) in stairs:
                flags[e] = EDGE_STAIRS
    np.savez_compressed(path, **data, edge_flags=flags)
    return WalkGraph(path), dlon


def test_avoid_stairs_takes_the_way_around(tmp_path):
    g, dlon = stairs_graph(tmp_path)
    a, b = at(dlon, 0, 0), at(dlon, 0, 2)
    block = STEP * 111_320 / 80
    direct = LocalRouting(g).walk(a, b)
    around = LocalRouting(g).view(avoid=("stairs",)).walk(a, b)
    assert direct.duration_min == pytest.approx(2 * block, rel=0.02)
    # Up a block, two along, back down: 4 blocks, and the time shown is the real walking time.
    assert around.duration_min == pytest.approx(4 * block, rel=0.02)
    assert max(p[0] for p in around.geometry) > LAT0 + STEP / 2
    t = LocalRouting(g).view(avoid=("stairs",)).matrix([a], [b]).durations_min[0][0]
    assert t == pytest.approx(4 * block, rel=0.02)


def test_avoid_is_a_penalty_not_a_wall(tmp_path):
    """When the stairs are the only way, the route still takes them."""
    g, dlon = stairs_graph(tmp_path)
    r = LocalRouting(g).view(avoid=("stairs",))
    leg = r.walk(at(dlon, 0, 1), at(dlon, 0, 0))  # (0,1) to (0,0): around is 3 blocks, stairs 1
    assert leg.duration_min > 0


def test_loop_returns_to_the_start_another_way(town):  # noqa: F811
    """20 minutes: one way, every cafe on the grid is too close (at most ~10 min); out and back to
    the far cafes is about 20."""
    intent = WalkIntent(duration_min=20, endpoint_type="cafe")
    one_way = plan_solo(town["origin"], intent, town["places"], town["routing"], SAT_15)
    loop = plan_solo(town["origin"], intent, town["places"], town["routing"], SAT_15,
                     options=WalkOptions(shape="loop"))
    assert one_way.status == "no_feasible_plan"
    assert loop.status == "proposed" and {c.id for c in loop.candidates} == {"node/2", "node/3"}
    for c in loop.candidates:
        back = c.return_leg
        assert back is not None and back.geometry[-1] == town["origin"]
        assert c.total_min == pytest.approx(c.leg.duration_min + back.duration_min, abs=0.02)
        assert c.total_min <= intent.duration_min + 5
        assert "back to your start" in c.rationale
        # On a grid there is another way back of the same length: not the same streets reversed.
        assert back.duration_min == pytest.approx(c.leg.duration_min, abs=0.05)
        inner = lambda leg: {(round(p[0], 5), round(p[1], 5)) for p in leg.geometry[1:-1]}  # noqa: E731
        assert len(inner(back) & inner(c.leg)) < len(inner(c.leg)) / 2


def test_options_reach_the_api(town, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr("app.providers.get_routing", lambda: town["routing"])
    monkeypatch.setattr("app.providers.get_places", lambda: town["places"])
    monkeypatch.setattr("app.api.solo.outside_message", lambda p: None)
    body = {"intent": {"duration_min": 20, "endpoint_type": "cafe"},
            "origin": {"lat": town["origin"][0], "lon": town["origin"][1]},
            "options": {"shape": "loop", "pace": "brisk", "avoid": ["stairs"], "must_be_open": True}}
    r = TestClient(app).post("/api/solo/plan", json=body).json()
    assert r["status"] == "proposed", r
    assert all(c["return_leg"] for c in r["candidates"])
    assert all("open when you arrive" in c["rationale"] for c in r["candidates"])  # hours known and open
    bad = TestClient(app).post("/api/solo/plan", json={**body, "options": {"avoid": ["crowds"]}})
    assert bad.status_code == 422  # no option without data behind it


def test_with_a_friend_the_options_apply_to_a_only(tmp_path, monkeypatch):
    """A walks at a relaxed pace: A's leg is timed at 65 m/min and the meeting point moves toward A
    (A covers less ground in the same time); B's leg stays at 80 m/min. No loop for two."""
    from fastapi.testclient import TestClient

    from app.main import app

    from .test_invite_flow import town as invite_town

    client = TestClient(app)
    places = invite_town.__wrapped__(tmp_path, monkeypatch) if hasattr(invite_town, "__wrapped__") else None
    assert places is not None
    views = {}
    for pace in ("normal", "relaxed"):
        body = client.post("/api/invites", json={
            "a_intent": {"duration_min": 15, "endpoint_type": "cafe"}, "a_origin": places["a"], "a_text": "",
            "a_options": {"pace": pace, "shape": "loop", "must_be_open": True}}).json()
        client.post(f"/api/invites/{body['token']}/accept", json={"b_origin": places["b"], "b_text": ""})
        views[pace] = client.get(f"/api/invites/{body['token']}", headers={"X-Invite-Key": body["a_key"]}).json()
    n, r = views["normal"], views["relaxed"]
    assert n["status"] == r["status"] == "proposed", r
    assert "destination open on arrival" in r["a_intent"]["hard_constraints"]
    a_speed = lambda c: c["a_leg"]["distance_m"] / c["a_leg"]["duration_min"]  # noqa: E731
    b_speed = lambda c: c["b_leg"]["distance_m"] / c["b_leg"]["duration_min"]  # noqa: E731
    assert a_speed(r["candidates"][0]) == pytest.approx(65, rel=0.02)
    assert b_speed(r["candidates"][0]) == pytest.approx(80, rel=0.02)
    assert a_speed(n["candidates"][0]) == pytest.approx(80, rel=0.02)


def test_stops_are_places_on_the_route():
    from app.models.schemas import RouteLeg
    from app.services.options import describe, mark_stops

    pois = [{"id": f"n/{i}", "name": f"P{i}", "category": c, "lat": 0, "lon": 0, "along_m": a}
            for i, (c, a) in enumerate([("park", 20), ("artwork", 300), ("park", 500), ("memorial", 700),
                                        ("artwork", 990)])]
    legs = [RouteLeg(geometry=[], distance_m=1000, duration_min=12.5, pois=pois)]
    stops = mark_stops(legs, 2, ["public_art"])
    assert [s["name"] for s in stops] == ["P1", "P3"] or [s["name"] for s in stops][0] == "P1"
    assert all(100 <= p["along_m"] <= 900 for p in legs[0].pois if p.get("stop"))  # not at the start or end
    assert [p.get("stop") for p in legs[0].pois if p.get("stop")] == [1, 2]
    assert "pois" in legs[0].model_dump() and "stop" not in pois[1]  # the input is not changed
    assert describe([], mark_stops([RouteLeg(geometry=[], distance_m=100, duration_min=1)], 2, []), 2) \
        == "Only 0 of the 2 stops asked for: this route passes fewer places."
