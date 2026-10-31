"""Flag walking-graph edges for the "Avoid" options: stairs, busy avenues, major transit hubs.

    python scripts/add_edge_flags.py              # updates deploy/data/nyc_graph.npz in place

Map data only, so the app can say "based on map data" and nothing more:
- STAIRS: an edge along an OSM way tagged highway=steps. The graph is simplified, so a flight of
  stairs is often inside a longer edge: such an edge is found by the stairs' inner nodes, which
  are points of its geometry.
- BUSY: an edge along a primary or trunk road (or its _link), or a sidewalk along one: at least
  BUSY_MIN_M long with both ends near the same primary/trunk street name (NYC maps most sidewalks
  as separate footways, so the road tag alone misses them).
- HUB: both ends within HUB_RADIUS_M of a major transit hub, the same proxy the planner uses for
  crowds (providers/snapshot_places.py: >= 6 named subway entrances within 150 m).

Reads the OpenStreetMap responses cached by scripts/build_graph.py (cache/osmnx). Writes
`edge_flags` (uint8 bit mask, CSR edge order). Map data © OpenStreetMap contributors, ODbL.
"""

import glob
import json
import math

import numpy as np
from _common import ROOT
from scipy.spatial import cKDTree

from app.providers.local_routing import EDGE_BUSY, EDGE_HUB, EDGE_STAIRS
from app.providers.snapshot_places import HUB_RADIUS_M, load_snapshot

GRAPH = ROOT / "deploy" / "data" / "nyc_graph.npz"
PLACES = ROOT / "deploy" / "data" / "nyc_places.json.gz"
BUSY_ROADS = {"primary", "primary_link", "trunk", "trunk_link"}
BUSY_MIN_M = 40.0  # shorter edges with a busy name at both ends are usually crossings, not walks along


def cached_ways():
    for f in sorted(glob.glob(str(ROOT / "cache" / "osmnx" / "*.json"))):
        try:
            d = json.load(open(f))
        except ValueError:
            continue
        if isinstance(d, dict):
            for e in d.get("elements", []):
                if e["type"] == "way" and (e.get("tags") or {}).get("highway"):
                    yield e


def main() -> int:
    with np.load(GRAPH) as d:
        data = {k: d[k] for k in d.files}
    indptr, indices, minutes = data["indptr"], data["indices"], data["minutes"]
    n = len(data["lat"])
    edge_of: dict[tuple[int, int], int] = {}
    for u in range(n):
        for e in range(indptr[u], indptr[u + 1]):
            edge_of[(u, int(indices[e]))] = e
    node_of = {int(o): i for i, o in enumerate(data["osmid"])}
    flags = np.zeros(len(indices), dtype=np.uint8)

    def flag_pair(u, v, bit):
        for key in ((u, v), (v, u)):
            if key in edge_of:
                flags[edge_of[key]] |= bit

    # Inner geometry points of every edge, to find ways that lie inside a simplified edge.
    gptr = data["geom_ptr"]
    inner_edge = np.repeat(np.arange(len(indices)), np.diff(gptr))
    cos = math.cos(math.radians(float(np.mean(data["lat"]))))
    inner_tree = cKDTree(np.column_stack((data["geom_lon"] * 111_320.0 * cos, data["geom_lat"] * 111_320.0)))
    coords = {}

    busy_names: set[str] = set()
    ways = list(cached_ways())
    for f in sorted(glob.glob(str(ROOT / "cache" / "osmnx" / "*.json"))):
        try:
            d = json.load(open(f))
        except ValueError:
            continue
        if isinstance(d, dict):
            coords.update({e["id"]: (e["lat"], e["lon"]) for e in d.get("elements", [])
                           if e["type"] == "node" and "lat" in e})
    for w in ways:
        tags = w["tags"]
        bit = EDGE_STAIRS if tags["highway"] == "steps" else EDGE_BUSY if tags["highway"] in BUSY_ROADS else 0
        if tags["highway"] in BUSY_ROADS and tags.get("name"):
            busy_names.add(tags["name"])
        if not bit:
            continue
        on_graph = [node_of[x] for x in w.get("nodes", []) if x in node_of]
        for u, v in zip(on_graph, on_graph[1:]):
            flag_pair(u, v, bit)
        inner = [coords[x] for x in w.get("nodes", []) if x not in node_of and x in coords]
        if inner:
            xy = np.array([(lo * 111_320.0 * cos, la * 111_320.0) for la, lo in inner])
            for hits in inner_tree.query_ball_point(xy, 1.0):
                for h in hits:
                    e = int(inner_edge[h])
                    flags[e] |= bit
                    u = int(np.searchsorted(indptr, e, side="right") - 1)
                    flag_pair(u, int(indices[e]), bit)

    # Sidewalks along busy streets, by the street names each node carries (scripts/add_street_names.py).
    names = str(data["street_names"]).split("\n")
    ptr, idx = data["node_names_ptr"], data["node_names"]
    busy_ids = {k for k, s in enumerate(names) if s in busy_names}
    node_busy = [frozenset(int(k) for k in idx[ptr[u]:ptr[u + 1]] if int(k) in busy_ids) for u in range(n)]
    m_per_min = float(data["walk_m_per_min"])
    for u in range(n):
        if not node_busy[u]:
            continue
        for e in range(indptr[u], indptr[u + 1]):
            v = int(indices[e])
            if minutes[e] * m_per_min >= BUSY_MIN_M and node_busy[u] & node_busy[v]:
                flags[e] |= EDGE_BUSY

    snap = load_snapshot(PLACES)
    if snap._hubs is not None:
        xy = np.column_stack((data["lon"] * 111_320.0 * cos, data["lat"] * 111_320.0))
        near = np.array([bool(h) for h in snap._hubs.query_ball_point(xy, HUB_RADIUS_M)]) \
            if isinstance(snap._hubs, cKDTree) else np.zeros(n, bool)
        rows = np.repeat(np.arange(n), np.diff(indptr))
        flags[near[rows] & near[indices]] |= EDGE_HUB

    data["edge_flags"] = flags
    np.savez_compressed(GRAPH, **data)
    for name, bit in (("stairs", EDGE_STAIRS), ("busy", EDGE_BUSY), ("hub", EDGE_HUB)):
        print(f"{name}: {int(np.count_nonzero(flags & bit))} of {len(flags)} edges")
    print(f"busy street names: {len(busy_names)}; wrote {GRAPH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
