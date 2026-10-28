"""Measure the local engine: data file sizes, load time, memory, planner latency per pair.

    python scripts/measure_local.py
"""

import os
import time

import psutil

os.environ["USE_MOCKS"] = "false"

from _common import load_cases  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.providers.local_routing import LocalRouting, load_graph  # noqa: E402
from app.providers.snapshot_places import SnapshotPlaces, load_snapshot  # noqa: E402
from app.services.planner import plan_walk  # noqa: E402


def main() -> int:
    s = get_settings()
    proc = psutil.Process()
    rss0 = proc.memory_info().rss
    t = time.perf_counter()
    graph = load_graph(s.graph_path)
    t_graph = time.perf_counter() - t
    rss1 = proc.memory_info().rss
    t = time.perf_counter()
    snapshot = load_snapshot(s.places_snapshot_path)
    t_snap = time.perf_counter() - t
    rss2 = proc.memory_info().rss

    print(f"graph file   {graph.file_bytes / 1e6:.1f} MB, {len(graph.lat)} nodes, {graph.csr.nnz} edges")
    print(f"places file  {snapshot.file_bytes / 1e6:.2f} MB, {len(snapshot.meetup.places)} meetup, "
          f"{len(snapshot.destination.places)} destinations")
    print(f"load time    graph {t_graph:.2f} s, places {t_snap:.2f} s")
    print(f"memory (RSS) process before {rss0 / 1e6:.0f} MB, +{(rss1 - rss0) / 1e6:.0f} MB graph, "
          f"+{(rss2 - rss1) / 1e6:.0f} MB places, total {rss2 / 1e6:.0f} MB")

    print("\nplanner latency per pair (fresh routing instance = cold; same instance again = warm)")
    for case in load_cases():
        routing, places = LocalRouting(graph), SnapshotPlaces(snapshot)
        t = time.perf_counter()
        r = plan_walk(case["a"], case["b"], case["intent"], places, routing, case["depart_at"])
        cold = time.perf_counter() - t
        t = time.perf_counter()
        plan_walk(case["a"], case["b"], case["intent"], places, routing, case["depart_at"])
        warm = time.perf_counter() - t
        print(f"  {case['id']:4} {r.status:18} cold {cold * 1000:6.0f} ms   warm {warm * 1000:5.0f} ms")
    print(f"\npeak RSS after planning: {proc.memory_info().rss / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
