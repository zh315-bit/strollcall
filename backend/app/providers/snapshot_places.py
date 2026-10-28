"""Places from the local OpenStreetMap snapshot (built by scripts/build_graph.py).

Same interface as the Overpass provider. Queries whose circle leaves the snapshot's
bounding box go to the fallback provider (Overpass), or fail with places_unavailable.
Opening hours are as of the snapshot's fetched_at. Map data © OpenStreetMap contributors, ODbL.
"""

import gzip
import json
import logging
import math
import threading
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from app.core.errors import ProviderError
from app.models.schemas import Place
from app.providers.overpass import MAX_RADIUS_M, _check_types

log = logging.getLogger(__name__)

M_PER_DEG_LAT = 111_320.0


class _Index:
    def __init__(self, places: list[Place], cos_lat: float):
        self.places = places
        self.cos_lat = cos_lat
        xy = [(p.lon * M_PER_DEG_LAT * cos_lat, p.lat * M_PER_DEG_LAT) for p in places]
        self.tree = cKDTree(np.array(xy)) if places else None

    def within(self, lat: float, lon: float, radius_m: float) -> list[Place]:
        if self.tree is None:
            return []
        hits = self.tree.query_ball_point([lon * M_PER_DEG_LAT * self.cos_lat, lat * M_PER_DEG_LAT], radius_m)
        return [self.places[i] for i in hits]


class Snapshot:
    def __init__(self, path: Path):
        with gzip.open(path, "rt") as f:
            data = json.load(f)
        self.fetched_at = data["fetched_at"]
        self.bbox = tuple(data["bbox"])  # south, west, north, east
        cos_lat = math.cos(math.radians((self.bbox[0] + self.bbox[2]) / 2))
        self.meetup = _Index([Place.model_validate(p) for p in data["meetup"]], cos_lat)
        self.destination = _Index([Place.model_validate(p) for p in data["destination"]], cos_lat)
        self.file_bytes = path.stat().st_size

    def covers(self, lat: float, lon: float, radius_m: float) -> bool:
        s, w, n, e = self.bbox
        dlat = radius_m / M_PER_DEG_LAT
        dlon = radius_m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))
        return s <= lat - dlat and lat + dlat <= n and w <= lon - dlon and lon + dlon <= e


_snapshots: dict[Path, Snapshot] = {}
_lock = threading.Lock()


def load_snapshot(path: Path) -> Snapshot:
    with _lock:
        if path not in _snapshots:
            if not path.exists():
                raise ProviderError("places_unavailable", f"place snapshot not built: {path.name}")
            _snapshots[path] = Snapshot(path)
        return _snapshots[path]


def _sorted(places: list[Place]) -> list[Place]:
    return sorted(places, key=lambda p: (p.category, p.name, p.id))


class SnapshotPlaces:
    name = "snapshot"

    def __init__(self, snapshot: Snapshot, fallback=None):
        self.snapshot = snapshot
        self.fallback = fallback  # Overpass provider, a callable returning one, or None

    def _outside(self):
        fb = self.fallback() if callable(self.fallback) else self.fallback
        if fb is None:
            raise ProviderError("places_unavailable", "outside the local place snapshot and no fallback")
        log.info("snapshot places: query outside the covered area; using %s", fb.name)
        return fb

    def meetup_candidates(self, lat: float, lon: float, radius_m: float) -> list[Place]:
        radius = min(radius_m, MAX_RADIUS_M)
        if not self.snapshot.covers(lat, lon, radius):
            return self._outside().meetup_candidates(lat, lon, radius_m)
        return _sorted(self.snapshot.meetup.within(lat, lon, radius))

    def destination_candidates(
        self, lat: float, lon: float, radius_m: float, types: list[str] | None = None
    ) -> list[Place]:
        types = _check_types(types)
        radius = min(radius_m, MAX_RADIUS_M)
        if not self.snapshot.covers(lat, lon, radius):
            return self._outside().destination_candidates(lat, lon, radius_m, types)
        return _sorted([p for p in self.snapshot.destination.within(lat, lon, radius) if p.category in types])

    places_near = destination_candidates
