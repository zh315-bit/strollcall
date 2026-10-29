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
def test_simulated_gps_walk_in_node():
    test_file = Path(__file__).parent / "js" / "walk.test.js"
    out = subprocess.run(["node", "--test", str(test_file)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
