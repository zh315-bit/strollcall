import gzip
import json
import math

import numpy as np
import pytest

from app.core.errors import ProviderError
from app.models.schemas import RouteLeg, TravelMatrix
from app.providers.local_routing import LocalRouting, WalkGraph
from app.providers.snapshot_places import SnapshotPlaces, Snapshot

LAT0, LON0, STEP = 40.7300, -74.0000, 0.001  # ~111 m north-south
M_PER_DEG = 111_320.0
N = 5


def grid_graph(path, extra_isolated=True):
    """5x5 street grid, ~111 m blocks, plus one isolated node; one edge has a bend."""
    cos = math.cos(math.radians(LAT0))
    dlon = STEP / cos  # same ~111 m east-west
    lat, lon = [], []
    for i in range(N):
        for j in range(N):
            lat.append(LAT0 + i * STEP)
            lon.append(LON0 + j * dlon)
    if extra_isolated:
        lat.append(LAT0 + 2 * STEP + 0.0004)  # near the grid but not connected
        lon.append(LON0 + 2.5 * dlon)
    edges = {}
    for i in range(N):
        for j in range(N):
            u = i * N + j
            for di, dj in ((0, 1), (1, 0)):
                if i + di < N and j + dj < N:
                    v = (i + di) * N + (j + dj)
                    edges[(u, v)] = edges[(v, u)] = STEP * M_PER_DEG / 80
    keys = sorted(edges)
    n = len(lat)
    indptr = np.zeros(n + 1, dtype=np.int64)
    for u, _ in keys:
        indptr[u + 1] += 1
    indptr = np.cumsum(indptr)
    geom_counts = [1 if k == (0, 1) else 0 for k in keys]  # bend on edge 0->1
    geom_ptr = np.concatenate([[0], np.cumsum(geom_counts)])
    np.savez_compressed(
        path, lat=np.array(lat), lon=np.array(lon), indptr=indptr,
        indices=np.array([k[1] for k in keys], dtype=np.int32),
        minutes=np.array([edges[k] for k in keys], dtype=np.float32),
        geom_ptr=geom_ptr, geom_lat=np.array([LAT0 + 0.0001], dtype=np.float32),
        geom_lon=np.array([LON0 + dlon / 2], dtype=np.float32),
        bbox=np.array([LAT0, LON0, LAT0 + 0.004, LON0 + 4 * dlon]),
        built_at=np.array("2026-10-28T00:00:00+00:00"), walk_m_per_min=np.array(80.0),
    )
    return WalkGraph(path), dlon


@pytest.fixture
def graph(tmp_path):
    return grid_graph(tmp_path / "g.npz")


class FakeFallback:
    name = "ors"

    def __init__(self):
        self.calls = 0

    def matrix(self, sources, destinations):
        self.calls += 1
        return TravelMatrix(durations_min=[[1.0]], distances_m=[[80.0]])

    def walk(self, start, end):
        self.calls += 1
        return RouteLeg(geometry=[start, end], distance_m=80, duration_min=1)


def node(graph_dlon, i, j):
    g, dlon = graph_dlon
    return (LAT0 + i * STEP, LON0 + j * dlon)


def test_matrix_times_follow_the_grid(graph):
    routing = LocalRouting(graph[0])
    block = STEP * M_PER_DEG / 80  # minutes per block
    m = routing.matrix([node(graph, 0, 0)], [node(graph, 0, 2), node(graph, 3, 4)])
    assert m.durations_min[0][0] == pytest.approx(2 * block, abs=0.02)
    assert m.durations_min[0][1] == pytest.approx(7 * block, abs=0.02)
    assert m.distances_m[0][1] == pytest.approx(7 * block * 80, rel=0.01)


def test_snap_walk_is_added(graph):
    routing = LocalRouting(graph[0])
    lat, lon = node(graph, 0, 0)
    m = routing.matrix([(lat + 0.0003, lon)], [(lat, lon)])  # ~33 m off the node
    assert m.durations_min[0][0] == pytest.approx(33.4 / 80, abs=0.05)


def test_walk_geometry_uses_edge_geometry_and_endpoints(graph):
    routing = LocalRouting(graph[0])
    start, end = node(graph, 0, 0), node(graph, 0, 1)
    leg = routing.walk(start, end)
    assert leg.geometry[0] == start and leg.geometry[-1] == end
    assert any(abs(p[0] - (LAT0 + 0.0001)) < 1e-5 for p in leg.geometry)  # the bend (float32, ~0.4 m)
    assert routing.walk(start, end) is leg  # cached


def test_unreachable_node(graph):
    g, dlon = graph
    routing = LocalRouting(g)
    isolated = (LAT0 + 2 * STEP + 0.0004, LON0 + 2.5 * dlon)
    m = routing.matrix([node(graph, 0, 0)], [isolated])
    assert m.durations_min == [[None]]
    with pytest.raises(ProviderError) as e:
        routing.walk(node(graph, 0, 0), isolated)
    assert e.value.code == "no_route"


def test_outside_coverage_uses_fallback_then_fails(graph):
    far = (LAT0 + 0.05, LON0)  # ~5.5 km away
    fb = FakeFallback()
    routing = LocalRouting(graph[0], fallback=fb)
    assert routing.matrix([far], [node(graph, 0, 0)]).durations_min == [[1.0]]
    assert routing.walk(far, node(graph, 0, 0)).duration_min == 1
    assert fb.calls == 2
    with pytest.raises(ProviderError) as e:
        LocalRouting(graph[0], fallback=None).walk(far, node(graph, 0, 0))
    assert e.value.code == "routing_unavailable"


def test_snap_limit_is_200m(graph):
    g = graph[0]
    lat, lon = node(graph, 0, 0)
    assert g.snap((lat - 150 / M_PER_DEG, lon))[1] == pytest.approx(150, abs=2)
    with pytest.raises(Exception):
        g.snap((lat - 250 / M_PER_DEG, lon))


def snapshot_file(path):
    def place(pid, lat, lon, cat):
        return {"id": pid, "name": pid, "lat": lat, "lon": lon, "category": cat,
                "opening_hours": None, "tags": {}, "fetched_at": "2026-10-28T12:00:00+00:00"}
    data = {
        "fetched_at": "2026-10-28T12:00:00+00:00", "bbox": [40.70, -74.02, 40.76, -73.96],
        "meetup": [place("way/1", 40.7300, -74.0000, "park"), place("node/2", 40.7400, -74.0000, "plaza")],
        "destination": [place("node/3", 40.7302, -74.0000, "cafe"), place("node/4", 40.7303, -74.0001, "bakery")],
    }
    with gzip.open(path, "wt") as f:
        json.dump(data, f)
    return Snapshot(path)


def test_snapshot_radius_and_types(tmp_path):
    places = SnapshotPlaces(snapshot_file(tmp_path / "p.json.gz"))
    assert [p.id for p in places.meetup_candidates(40.7300, -74.0000, 300)] == ["way/1"]
    assert [p.id for p in places.destination_candidates(40.7300, -74.0000, 300, ["cafe"])] == ["node/3"]
    assert len(places.destination_candidates(40.7300, -74.0000, 300)) == 2
    assert places.destination_candidates(40.7300, -74.0000, 300)[0].fetched_at is not None


def test_snapshot_outside_bbox_uses_fallback(tmp_path):
    class Fallback:
        name = "overpass"

        def meetup_candidates(self, lat, lon, r):
            return ["fallback"]

    places = SnapshotPlaces(snapshot_file(tmp_path / "p.json.gz"), fallback=Fallback())
    assert places.meetup_candidates(40.80, -74.0, 300) == ["fallback"]
    with pytest.raises(ProviderError) as e:
        SnapshotPlaces(places.snapshot).meetup_candidates(40.80, -74.0, 300)
    assert e.value.code == "places_unavailable"


def test_factories_respect_use_mocks():
    from app.providers import get_places, get_routing

    assert get_routing().name == "mock" and get_places().name == "mock"
