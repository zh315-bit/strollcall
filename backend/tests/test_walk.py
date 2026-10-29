"""Walking guidance: the re-plan endpoint, and the browser logic's simulated GPS walk (Node)."""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers.local_routing import LocalRouting

from .test_local_providers import LAT0, LON0, STEP, grid_graph

client = TestClient(app)


def test_replan_routes_from_the_current_position_on_the_local_graph(tmp_path, monkeypatch, caplog):
    g, dlon = grid_graph(tmp_path / "g.npz")
    monkeypatch.setattr("app.providers.get_routing", lambda: LocalRouting(g))
    here, target = {"lat": LAT0 + STEP, "lon": LON0 + 0.00005}, {"lat": LAT0 + 3 * STEP, "lon": LON0 + 3 * dlon}
    r = client.post("/api/walk/route", json={"origin": here, "target": target})
    assert r.status_code == 200
    leg = r.json()
    assert leg["geometry"][0] == [here["lat"], here["lon"]] and leg["geometry"][-1] == [target["lat"], target["lon"]]
    assert leg["duration_min"] > 0
    assert str(here["lat"]) not in caplog.text  # positions are never logged

    far = {"lat": LAT0 + 1.0, "lon": LON0}
    assert client.post("/api/walk/route", json={"origin": far, "target": target}).status_code == 422


def test_replan_needs_the_local_graph():
    # USE_MOCKS: the mock router has no graph
    r = client.post("/api/walk/route", json={"origin": {"lat": 40.7, "lon": -74}, "target": {"lat": 40.71, "lon": -74}})
    assert r.status_code == 503


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_walk_logic_and_walking_screen_in_node():
    """walk.test.js: simulated GPS walks; walk_screen.test.js: the walking screen's page/CSS contract."""
    files = sorted(str(p) for p in (Path(__file__).parent / "js").glob("*.test.js"))
    assert len(files) >= 2
    out = subprocess.run(["node", "--test", *files], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


def test_route_pois_finds_a_park_by_its_edge_and_orders_by_distance(tmp_path):
    import gzip
    import json

    from app.providers.route_pois import RoutePois

    m = 1 / 111_320
    # A route east along lat 40.75; a park whose edge is 30 m north of it (centre 300 m north),
    # a statue 20 m south further along, and an artwork 200 m away (not along the route).
    park_edge = [[40.75 + 30 * m, -73.9800 + i * 0.0002] for i in range(5)]
    data = {"pois": [
        {"id": "way/1", "name": "Big Park", "category": "park", "lat": 40.75 + 300 * m, "lon": -73.9796, "pts": park_edge},
        {"id": "node/2", "name": "A Statue", "category": "artwork", "lat": 40.75 - 20 * m, "lon": -73.9760,
         "pts": [[40.75 - 20 * m, -73.9760]]},
        {"id": "node/3", "name": "Far Away", "category": "artwork", "lat": 40.75 + 200 * m, "lon": -73.9770,
         "pts": [[40.75 + 200 * m, -73.9770]]},
    ]}
    path = tmp_path / "pois.json.gz"
    with gzip.open(path, "wt") as f:
        json.dump(data, f)
    found = RoutePois(path).along([(40.75, -73.9810), (40.75, -73.9740)])
    assert [p["name"] for p in found] == ["Big Park", "A Statue"]
    assert found[0]["along_m"] < found[1]["along_m"]
    assert abs(found[0]["lat"] - (40.75 + 30 * m)) < 1e-6  # the park's point nearest the route, not its centre


def test_other_persons_pois_are_not_shown():
    from app.models.schemas import RouteLeg
    from app.services.invites import trim_start

    leg = RouteLeg(geometry=[(40.75, -73.98), (40.751, -73.98), (40.76, -73.98)], distance_m=1100, duration_min=14,
                   steps=[{"text": "Head north"}], pois=[{"id": "node/1"}])
    trimmed = trim_start(leg)
    assert trimmed.steps == [] and trimmed.pois == []
