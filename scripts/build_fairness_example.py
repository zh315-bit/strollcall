"""The home page's "Meet halfway, fairly" example: frontend/data/fairness_example.json.

From the benchmark pairs (fixtures/nyc_origins.json: public start points, subway stations and
parks, never home addresses) it picks the pair whose geographic midpoint is most unfair in walking
time while our planner still proposes a fair plan, and measures both on the local walking graph:

- the geographic midpoint (the average of the two start points) snapped to the nearest street
  node, with A's and B's real walking times and routes to it
- the planner's top meeting point (as scripts/benchmark.py runs it: case intent, fixed depart_at),
  with A's and B's walking times and routes, and the walk together to the destination

Also a light street grid around them (graph edges, straight node to node) for the page to draw.
The page reads only this file; nothing is planned at page load. Run once, commit the output:

    python scripts/build_fairness_example.py
"""

import json
import sys
from datetime import date
from pathlib import Path

from _common import ROOT, load_cases

from app.core.config import get_settings  # noqa: E402
from app.providers.local_routing import LocalRouting, load_graph  # noqa: E402
from app.providers.snapshot_places import SnapshotPlaces, load_snapshot  # noqa: E402
from app.services.planner import plan_walk  # noqa: E402

OUT = ROOT / "frontend" / "data" / "fairness_example.json"
GOOD_PLAN_GAP_MIN = 2.0  # "a good plan": proposed, and the two arrive within this of each other
STREET_PAD = 0.0025  # degrees around the routes that the street grid covers (~250 m)


def data_path(configured: Path, name: str) -> Path:
    return configured if configured.exists() else ROOT / "deploy" / "data" / name


def pts(geometry) -> list[list[float]]:
    return [[round(la, 5), round(lo, 5)] for la, lo in geometry]


def main() -> int:
    s = get_settings()
    graph = load_graph(data_path(s.graph_path, "nyc_graph.npz"))
    snapshot = load_snapshot(data_path(s.places_snapshot_path, "nyc_places.json.gz"))

    measured = []
    for case in load_cases():
        a, b = case["a"], case["b"]
        routing = LocalRouting(graph)
        node, _ = graph.snap(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        mid = (float(graph.lat[node]), float(graph.lon[node]))
        to_mid = routing.walk(a, mid), routing.walk(b, mid)
        plan = plan_walk(a, b, case["intent"], SnapshotPlaces(snapshot), LocalRouting(graph), case["depart_at"])
        top = plan.candidates[0] if plan.status == "proposed" and plan.candidates else None
        gap = abs(to_mid[0].duration_min - to_mid[1].duration_min)
        good = top is not None and abs(top.a_leg.duration_min - top.b_leg.duration_min) <= GOOD_PLAN_GAP_MIN
        print(f"{case['id']}: midpoint {to_mid[0].duration_min:.1f} / {to_mid[1].duration_min:.1f} min "
              f"(gap {gap:.1f}); plan {plan.status}" + (f", {top.a_leg.duration_min:.1f} / {top.b_leg.duration_min:.1f}" if top else ""))
        if good:
            measured.append((gap, case, mid, to_mid, plan, top))
    if not measured:
        print("no pair has a good plan", file=sys.stderr)
        return 1
    gap, case, mid, to_mid, plan, top = max(measured, key=lambda m: m[0])
    meet, dest = plan.places[top.meeting_place_id], plan.places[top.endpoint_place_id]
    pair = case["pair"]

    lines = [to_mid[0].geometry, to_mid[1].geometry, top.a_leg.geometry, top.b_leg.geometry, top.shared_leg.geometry]
    lats = [p[0] for g in lines for p in g]
    lons = [p[1] for g in lines for p in g]
    box = (min(lats) - STREET_PAD, min(lons) - STREET_PAD, max(lats) + STREET_PAD, max(lons) + STREET_PAD)
    inside = (graph.lat >= box[0]) & (graph.lat <= box[2]) & (graph.lon >= box[1]) & (graph.lon <= box[3])
    streets, seen = [], set()
    for u in map(int, inside.nonzero()[0]):
        for v in map(int, graph.indices[graph.indptr[u]:graph.indptr[u + 1]]):
            if inside[v] and (v, u) not in seen:
                seen.add((u, v))
                streets.append(pts([(graph.lat[u], graph.lon[u]), (graph.lat[v], graph.lon[v])]))

    example = {
        "_note": ("Measured on the local OpenStreetMap walking graph by scripts/build_fairness_example.py. "
                  f"Benchmark pair {case['id']} (fixtures/nyc_origins.json: public places only), "
                  f"intent and depart_at from fixtures/benchmark_cases.json. Walking times at "
                  f"{graph.m_per_min:.0f} m/min. Route data © OpenStreetMap contributors (ODbL)."),
        "pair": case["id"],
        "generated": date.today().isoformat(),
        "bbox": [round(x, 5) for x in box],
        "a": {"name": pair["a"]["name"], "lat": case["a"][0], "lon": case["a"][1]},
        "b": {"name": pair["b"]["name"], "lat": case["b"][0], "lon": case["b"][1]},
        "midpoint": {"lat": round(mid[0], 5), "lon": round(mid[1], 5),
                     "a_min": round(to_mid[0].duration_min, 1), "b_min": round(to_mid[1].duration_min, 1),
                     "a_route": pts(to_mid[0].geometry), "b_route": pts(to_mid[1].geometry)},
        "meeting": {"name": meet.name, "lat": meet.lat, "lon": meet.lon,
                    "a_min": round(top.a_leg.duration_min, 1), "b_min": round(top.b_leg.duration_min, 1),
                    "a_route": pts(top.a_leg.geometry), "b_route": pts(top.b_leg.geometry)},
        "destination": {"name": dest.name, "category": dest.category, "lat": dest.lat, "lon": dest.lon,
                        "shared_min": round(top.shared_leg.duration_min, 1), "route": pts(top.shared_leg.geometry)},
        "streets": streets,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(example, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"picked {case['id']} (midpoint gap {gap:.1f} min): {len(streets)} street segments, "
          f"{OUT.stat().st_size / 1024:.0f} KB -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
