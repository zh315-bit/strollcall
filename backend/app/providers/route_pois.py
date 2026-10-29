"""Points of interest near a walking route (parks, historic sites, artworks, memorials, landmarks).

Data: deploy/data/nyc_pois.json.gz from scripts/build_route_pois.py (OpenStreetMap, ODbL). Each
POI has sample points along its outline, so a route passing a park's edge finds the park. A POI
is "along the route" when a sample point lies within NEAR_M of the line.
"""

import gzip
import json
import logging
import math
import threading
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from app.core.geo import haversine_m

log = logging.getLogger(__name__)

NEAR_M = 40.0
STEP_M = 10.0  # the route is sampled this often
M_PER_DEG = 111_320.0


class RoutePois:
    def __init__(self, path: Path):
        with gzip.open(path, "rt") as f:
            data = json.load(f)
        self.pois = data["pois"]
        lat0 = float(np.mean([p["lat"] for p in self.pois])) if self.pois else 40.75
        self.cos = math.cos(math.radians(lat0))
        owner, xy = [], []
        for k, p in enumerate(self.pois):
            for la, lo in p["pts"]:
                owner.append(k)
                xy.append((lo * M_PER_DEG * self.cos, la * M_PER_DEG))
        self.owner = np.array(owner, dtype=np.int32)
        self.pts = np.array([pt for p in self.pois for pt in p["pts"]])
        self.tree = cKDTree(np.array(xy)) if xy else None

    def along(self, geometry: list[tuple[float, float]], near_m: float = NEAR_M) -> list[dict]:
        """POIs within near_m of the line, in the order the walker reaches them:
        {id, name, category, lat, lon (the POI's point nearest the route), along_m}."""
        if self.tree is None or len(geometry) < 2:
            return []
        samples, along, walked = [], [], 0.0
        for a, b in zip(geometry, geometry[1:]):
            seg = haversine_m(*a, *b)
            k = max(1, int(seg // STEP_M))
            for i in range(k):
                samples.append((a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k))
                along.append(walked + seg * i / k)
            walked += seg
        samples.append(geometry[-1])
        along.append(walked)
        xy = np.array([(lo * M_PER_DEG * self.cos, la * M_PER_DEG) for la, lo in samples])
        best: dict[int, tuple[float, float, int]] = {}  # poi -> (along, distance, sample point)
        for i, hits in enumerate(self.tree.query_ball_point(xy, near_m)):
            for h in hits:
                k = int(self.owner[h])
                if k not in best:
                    best[k] = (along[i], 0.0, h)
        out = []
        for k, (at, _, h) in sorted(best.items(), key=lambda kv: kv[1][0]):
            p = self.pois[k]
            out.append({"id": p["id"], "name": p["name"], "category": p["category"],
                        "lat": float(self.pts[h][0]), "lon": float(self.pts[h][1]), "along_m": round(at, 1)})
        return out


_loaded: dict[Path, RoutePois | None] = {}
_lock = threading.Lock()


def load_route_pois(path: Path) -> RoutePois | None:
    """Loaded once; None (no POIs on routes) when the file is missing."""
    with _lock:
        if path not in _loaded:
            if path.exists():
                _loaded[path] = RoutePois(path)
            else:
                log.warning("route POIs not found: %s; walks show no points of interest", path.name)
                _loaded[path] = None
        return _loaded[path]
