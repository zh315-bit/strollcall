"""Compare local-graph walking times with recorded ORS matrix entries (fixtures/).

    python scripts/validate_local_routing.py
"""

import json
import statistics
from collections import defaultdict

from _common import ROOT

from app.core.config import get_settings
from app.providers.local_routing import LocalRouting, load_graph


def parse(key: str):
    a, b = key.split("|")
    return tuple(map(float, a.split(","))), tuple(map(float, b.split(",")))


def main() -> int:
    elements = json.loads((ROOT / "fixtures" / "ors_matrix_elements.json").read_text())
    routing = LocalRouting(load_graph(get_settings().graph_path))
    by_source = defaultdict(list)
    for key, value in elements.items():
        src, dst = parse(key)
        by_source[src].append((dst, value))

    diffs, rel, skipped = [], [], {"ors_no_route": 0, "local_no_route": 0, "same_point": 0}
    for src, items in by_source.items():
        m = routing.matrix([src], [d for d, _ in items])
        for (dst, ors), local in zip(items, m.durations_min[0]):
            if ors is None:
                skipped["ors_no_route"] += 1
            elif local is None:
                skipped["local_no_route"] += 1
            elif ors[0] < 0.5:
                skipped["same_point"] += 1
            else:
                diffs.append(abs(local - ors[0]))
                rel.append(local / ors[0])
    diffs.sort()
    p90 = diffs[int(0.9 * (len(diffs) - 1))]
    print(f"compared {len(diffs)} of {len(elements)} ORS matrix entries; skipped {skipped}")
    print(f"absolute difference: median {statistics.median(diffs):.2f} min, P90 {p90:.2f} min, max {diffs[-1]:.2f} min")
    print(f"local / ORS time ratio: median {statistics.median(rel):.3f}")
    snaps = sorted(routing.snap_m)
    print(f"snap distance: median {statistics.median(snaps):.0f} m, max {snaps[-1]:.0f} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
