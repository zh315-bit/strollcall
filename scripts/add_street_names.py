"""Add every node's nearby street names to an existing walking graph (for turn instructions).

    python scripts/add_street_names.py              # data/nyc_graph.npz, then copy to deploy/data

Same method and data as scripts/build_graph.py (names of drive streets within 20 m, from the
cached OSMnx download), without rebuilding the graph. Checks that the names reproduce the
graph's existing intersection labels before writing. Map data © OpenStreetMap contributors, ODbL.
"""

import argparse
import shutil

import numpy as np
import osmnx as ox
from _common import ROOT
from build_graph import intersection_labels, node_name_arrays, street_names_near


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--graph", default=str(ROOT / "data" / "nyc_graph.npz"))
    p.add_argument("--copy-to-deploy", action="store_true", default=True)
    args = p.parse_args()
    # Same settings as build_graph.py: the timeout is part of the query, so of the cache key.
    ox.settings.http_user_agent = "StrollCall/0.1 (Meta AI hackathon prototype; one-off graph build)"
    ox.settings.requests_timeout = 300
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(ROOT / "cache" / "osmnx")

    with np.load(args.graph) as d:
        data = {k: d[k] for k in d.files}
    lat, lon, bbox = data["lat"], data["lon"], tuple(float(x) for x in data["bbox"])
    found = street_names_near(bbox, lat, lon, np.arange(len(lat)))
    degree = np.diff(data["indptr"])
    labels = intersection_labels(bbox, lat, lon, degree, found)
    old_table = str(data["labels"]).split("\n")
    old = {i: old_table[k] for i, k in enumerate(data["node_label"]) if k >= 0}
    same = sum(labels.get(i) == v for i, v in old.items())
    print(f"existing intersection labels reproduced: {same}/{len(old)}")
    if same < 0.99 * len(old):
        raise SystemExit("names differ from the original build; not writing")
    data.update(node_name_arrays(found, len(lat)))
    named = int(np.count_nonzero(np.diff(data["node_names_ptr"])))
    np.savez_compressed(args.graph, **data)
    print(f"wrote {args.graph}: {named}/{len(lat)} nodes have a street name")
    if args.copy_to_deploy:
        shutil.copy(args.graph, ROOT / "deploy" / "data" / "nyc_graph.npz")
        print("copied to deploy/data/nyc_graph.npz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
