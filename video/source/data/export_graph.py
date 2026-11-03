"""Export the walking graph's street geometry for Manhattan (deploy/data/nyc_graph.npz) for Scene 8:
every edge as a polyline, each undirected street segment once. Writes video/assets/data/walking_graph_manhattan.json."""

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
z = np.load(ROOT / "deploy" / "data" / "nyc_graph.npz", allow_pickle=True)
lat, lon, indptr, indices = z["lat"], z["lon"], z["indptr"], z["indices"]
gptr, glat, glon = z["geom_ptr"], z["geom_lat"], z["geom_lon"]
S, W, N, E = 40.700, -74.020, 40.880, -73.905  # Manhattan and its edge
segs, seen = [], set()
for u in range(len(lat)):
    if not (S <= lat[u] <= N and W <= lon[u] <= E):
        continue
    for k in range(indptr[u], indptr[u + 1]):
        v = int(indices[k])
        if (v, u) in seen:
            continue
        seen.add((u, v))
        pts = [(float(lat[u]), float(lon[u]))]
        pts += list(zip(glat[gptr[k]:gptr[k + 1]].tolist(), glon[gptr[k]:gptr[k + 1]].tolist()))
        pts.append((float(lat[v]), float(lon[v])))
        segs.append([[round(a, 5), round(b, 5)] for a, b in pts])
nodes = int(((lat >= S) & (lat <= N) & (lon >= W) & (lon <= E)).sum())
out = {"source": "deploy/data/nyc_graph.npz (OpenStreetMap, ODbL)", "bbox": [S, W, N, E],
       "graph_nodes_total": int(len(lat)), "nodes_in_bbox": nodes, "segments": len(segs), "lines": segs}
(ROOT / "video" / "assets" / "data" / "walking_graph_manhattan.json").write_text(json.dumps(out, separators=(",", ":")))
print({k: v for k, v in out.items() if k != "lines"})
