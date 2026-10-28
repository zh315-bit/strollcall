"""Walking times on a local OpenStreetMap graph (built by scripts/build_graph.py).

Same interface as the ORS provider (`walk`, `matrix`), with no daily quota. Points are
snapped to the nearest graph node with a KD-tree; a point more than SNAP_MAX_M from the
network is outside the covered area and goes to the fallback provider (ORS), or fails
with routing_unavailable. The walk from a point to its node is added at the same speed.

Map data © OpenStreetMap contributors, ODbL.
"""

import logging
import math
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from app.core.errors import ProviderError
from app.models.schemas import RouteLeg, TravelMatrix
from app.providers.ors import route_key

log = logging.getLogger(__name__)

Point = tuple[float, float]  # (lat, lon)
SNAP_MAX_M = 200.0
SEARCH_LIMIT_MIN = 40.0  # bounded Dijkstra
M_PER_DEG_LAT = 111_320.0
CACHE_MAX = 20_000
DIJKSTRA_CACHE = 64  # recent single-source results kept for directions


class OutsideCoverage(Exception):
    pass


class WalkGraph:
    """The loaded graph: CSR adjacency in minutes, node coordinates, edge geometry."""

    def __init__(self, path: Path):
        data = np.load(path)
        self.lat, self.lon = data["lat"], data["lon"]
        self.indptr, self.indices, self.minutes = data["indptr"], data["indices"], data["minutes"]
        self.geom_ptr, self.geom_lat, self.geom_lon = data["geom_ptr"], data["geom_lat"], data["geom_lon"]
        self.m_per_min = float(data["walk_m_per_min"])
        self.osmid = data["osmid"] if "osmid" in data else np.arange(len(self.lat))
        self.node_label = data["node_label"] if "node_label" in data else np.full(len(self.lat), -1)
        self.labels = str(data["labels"]).split("\n") if "labels" in data else []
        self.degree = np.diff(self.indptr)
        self.bbox = tuple(float(x) for x in data["bbox"])
        n = len(self.lat)
        self.csr = csr_matrix((self.minutes, self.indices, self.indptr), shape=(n, n))
        self.cos_lat = math.cos(math.radians(float(np.mean(self.lat))))
        self.tree = cKDTree(np.column_stack(self._xy(self.lat, self.lon)))
        self.file_bytes = path.stat().st_size

    def _xy(self, lat, lon):
        return np.asarray(lon) * M_PER_DEG_LAT * self.cos_lat, np.asarray(lat) * M_PER_DEG_LAT

    def snap(self, p: Point) -> tuple[int, float]:
        """Nearest node and the straight distance to it in meters."""
        x, y = self._xy(p[0], p[1])
        dist, node = self.tree.query([float(x), float(y)])
        if dist > SNAP_MAX_M:
            raise OutsideCoverage(f"point is {dist:.0f} m from the walking network")
        return int(node), float(dist)

    def intersection_name(self, u: int) -> str | None:
        """'E 86th St & York Ave' for an intersection node, from the build step; else None."""
        k = int(self.node_label[u])
        return self.labels[k] if k >= 0 else None

    def edge_geometry(self, u: int, v: int) -> list[Point]:
        row = slice(self.indptr[u], self.indptr[u + 1])
        hits = np.nonzero(self.indices[row] == v)[0]
        if not len(hits):
            return []
        e = self.indptr[u] + hits[0]
        g = slice(self.geom_ptr[e], self.geom_ptr[e + 1])
        return [(float(a), float(b)) for a, b in zip(self.geom_lat[g], self.geom_lon[g])]


_graphs: dict[Path, WalkGraph] = {}
_lock = threading.Lock()


def load_graph(path: Path) -> WalkGraph:
    """Loaded once per process."""
    with _lock:
        if path not in _graphs:
            if not path.exists():
                raise ProviderError("routing_unavailable", f"walking graph not built: {path.name}")
            _graphs[path] = WalkGraph(path)
        return _graphs[path]


class LocalRouting:
    name = "local"

    def __init__(self, graph: WalkGraph, fallback=None):
        self.graph = graph
        self.fallback = fallback  # ORS provider, or a callable returning one, or None
        self.legs: dict[str, RouteLeg] = {}
        self.elements: dict[str, tuple[float, float] | None] = {}
        self._trees: OrderedDict[int, tuple[np.ndarray, np.ndarray]] = OrderedDict()
        self.snap_m: list[float] = []  # recent snap distances, for reporting

    def _fallback(self, why: str):
        fb = self.fallback() if callable(self.fallback) else self.fallback
        if fb is None:
            raise ProviderError("routing_unavailable", f"outside the local map ({why}) and no fallback")
        log.info("local routing: point outside the covered area; using %s", fb.name)
        return fb

    def _search(self, source: int) -> tuple[np.ndarray, np.ndarray]:
        """Bounded single-source Dijkstra: minutes to every node and predecessors."""
        if source in self._trees:
            self._trees.move_to_end(source)
            return self._trees[source]
        dist, pred = dijkstra(self.graph.csr, directed=True, indices=source,
                              limit=SEARCH_LIMIT_MIN, return_predecessors=True)
        self._trees[source] = (dist, pred)
        if len(self._trees) > DIJKSTRA_CACHE:
            self._trees.popitem(last=False)
        return dist, pred

    def equal_time_nodes(self, a: Point, b: Point, max_minutes: float, max_gap: float):
        """Nodes A and B both reach within max_minutes, arriving within max_gap of each other.

        Returns (node indices, tA, tB) as arrays; times include the snap walk.
        Raises OutsideCoverage when A or B is off the local map.
        """
        (na, sa), (nb, sb) = self.graph.snap(a), self.graph.snap(b)
        speed = self.graph.m_per_min
        ta = self._search(na)[0] + sa / speed
        tb = self._search(nb)[0] + sb / speed
        with np.errstate(invalid="ignore"):  # inf - inf for nodes neither reaches
            mask = np.isfinite(ta) & np.isfinite(tb) & (np.abs(ta - tb) <= max_gap) & (np.maximum(ta, tb) <= max_minutes)
        nodes = np.nonzero(mask)[0]
        return nodes, ta[nodes], tb[nodes]

    def matrix(self, sources: list[Point], destinations: list[Point]) -> TravelMatrix:
        try:
            src = [self.graph.snap(p) for p in sources]
            dst = [self.graph.snap(p) for p in destinations]
        except OutsideCoverage as e:
            return self._fallback(str(e)).matrix(sources, destinations)
        self.snap_m.extend(d for _, d in src + dst)

        speed = self.graph.m_per_min
        durations, distances = [], []
        for (s_node, s_snap), s in zip(src, sources):
            dist, _ = self._search(s_node)
            row_t, row_d = [], []
            for (d_node, d_snap), d in zip(dst, destinations):
                t = dist[d_node]
                if not np.isfinite(t):
                    value = None  # no walking path within SEARCH_LIMIT_MIN
                else:
                    minutes = float(t) + (s_snap + d_snap) / speed
                    value = (round(minutes, 2), round(minutes * speed, 1))
                self.elements[route_key(s, d)] = value
                row_t.append(None if value is None else value[0])
                row_d.append(None if value is None else value[1])
            durations.append(row_t)
            distances.append(row_d)
        if len(self.elements) > CACHE_MAX:
            self.elements.clear()
        return TravelMatrix(durations_min=durations, distances_m=distances)

    def walk(self, start: Point, end: Point) -> RouteLeg:
        key = route_key(start, end)
        if key in self.legs:
            return self.legs[key]
        try:
            (s_node, s_snap), (e_node, e_snap) = self.graph.snap(start), self.graph.snap(end)
        except OutsideCoverage as e:
            return self._fallback(str(e)).walk(start, end)
        dist, pred = self._search(s_node)
        if not np.isfinite(dist[e_node]):
            raise ProviderError("no_route", f"no walking path within {SEARCH_LIMIT_MIN:.0f} min")

        nodes = [e_node]
        while nodes[-1] != s_node:
            nodes.append(int(pred[nodes[-1]]))
        nodes.reverse()
        g = self.graph
        geometry: list[Point] = [start]
        for u, v in zip(nodes, nodes[1:]):
            geometry.append((float(g.lat[u]), float(g.lon[u])))
            geometry.extend(g.edge_geometry(u, v))
        geometry += [(float(g.lat[e_node]), float(g.lon[e_node])), end]

        minutes = float(dist[e_node]) + (s_snap + e_snap) / g.m_per_min
        leg = RouteLeg(geometry=geometry, distance_m=round(minutes * g.m_per_min, 1),
                       duration_min=round(minutes, 2))
        if len(self.legs) > CACHE_MAX:
            self.legs.clear()
        self.legs[key] = leg
        return leg
