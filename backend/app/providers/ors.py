"""Walking times from openrouteservice (foot-walking profile): directions and matrix.

Points are rounded to 4 decimals (about 11 m) before they are sent, and results are
cached in memory under those rounded points, so a cached value is exactly what ORS
returned for them. Limits: 40 requests per minute each for directions and matrix and at
most 3,500 matrix elements per request (openrouteservice.org/plans). Daily quotas are
per key: on 2026-10-28 our key reported x-ratelimit-limit 200 for directions, and the
matrix endpoint answered 403 "Quota exceeded" after a few dozen calls, so the daily
budget is far smaller than the published 2,000 / 500.
"""

import logging
import threading
import time
from collections import deque

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ProviderError
from app.core.geo import coord_key
from app.models.schemas import RouteLeg, TravelMatrix

log = logging.getLogger(__name__)

BASE_URL = "https://api.openrouteservice.org/v2"
PROFILE = "foot-walking"
CACHE_MAX = 20_000
MAX_MATRIX_ELEMENTS = 3500
RATE_LIMIT_PER_MIN = 40
TRANSIENT_STATUSES = (429, 500, 502, 503, 504)
RETRY_WAIT_S = 2.0

Point = tuple[float, float]  # (lat, lon)


def route_key(start: Point, end: Point) -> str:
    return f"{coord_key(*start)}|{coord_key(*end)}"


def _rounded(p: Point) -> list[float]:
    """ORS wants [lon, lat]."""
    return [round(p[1], 4), round(p[0], 4)]


class RateLimiter:
    """At most `max_calls` per `period_s`, sliding window; waits (bounded by period_s)."""

    def __init__(self, max_calls: int, period_s: float = 60.0, clock=time.monotonic, sleep=time.sleep):
        self.max_calls, self.period_s = max_calls, period_s
        self.clock, self.sleep = clock, sleep
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            now = self.clock()
            while self.calls and now - self.calls[0] >= self.period_s:
                self.calls.popleft()
            if len(self.calls) >= self.max_calls:
                wait = self.period_s - (now - self.calls[0])
                log.info("ors rate limit: waiting %.1f s", wait)
                self.sleep(wait)
                self.calls.popleft()
            self.calls.append(self.clock())


class ORSProvider:
    name = "ors"

    def __init__(self, settings: Settings | None = None, http: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self._api_key = self.settings.ors_api_key.get_secret_value()
        if not self._api_key:
            raise ProviderError("routing_unavailable", "ORS_API_KEY is not set")
        self.http = http or httpx.Client(timeout=20.0)
        self.limiters = {
            "directions": RateLimiter(RATE_LIMIT_PER_MIN),
            "matrix": RateLimiter(RATE_LIMIT_PER_MIN),
        }
        self.legs: dict[str, RouteLeg] = {}
        # route_key -> (duration_min, distance_m), or None when ORS found no route
        self.elements: dict[str, tuple[float, float] | None] = {}

    def walk(self, start: Point, end: Point) -> RouteLeg:
        key = route_key(start, end)
        if key in self.legs:
            return self.legs[key]

        body = {"coordinates": [_rounded(start), _rounded(end)]}
        data = self._post("directions", f"{BASE_URL}/directions/{PROFILE}/geojson", body)
        features = data.get("features") or []
        if not features:
            raise ProviderError("no_route", "ORS returned no route")
        feature = features[0]
        summary = feature["properties"].get("summary", {})
        leg = RouteLeg(
            geometry=[(lat, lon) for lon, lat, *_ in feature["geometry"]["coordinates"]],
            distance_m=float(summary.get("distance", 0.0)),
            duration_min=round(float(summary.get("duration", 0.0)) / 60, 2),
        )
        log.info("ors: leg %.0f m, %.1f min", leg.distance_m, leg.duration_min)
        self._remember(self.legs, key, leg)
        return leg

    def matrix(self, sources: list[Point], destinations: list[Point]) -> TravelMatrix:
        """Walking minutes and meters from every source to every destination.

        An entry is None when ORS found no route between that pair.
        """
        if not sources or not destinations:
            raise ValueError("matrix needs at least one source and one destination")
        if len(sources) * len(destinations) > MAX_MATRIX_ELEMENTS:
            raise ValueError("matrix request exceeds the ORS element limit")

        keys = [[route_key(s, d) for d in destinations] for s in sources]
        if not all(k in self.elements for row in keys for k in row):
            self._fetch_matrix(sources, destinations, keys)
        else:
            log.info("ors matrix: %dx%d from cache", len(sources), len(destinations))

        durations = [[_get(self.elements[k], 0) for k in row] for row in keys]
        distances = [[_get(self.elements[k], 1) for k in row] for row in keys]
        return TravelMatrix(durations_min=durations, distances_m=distances)

    def _fetch_matrix(self, sources: list[Point], destinations: list[Point], keys) -> None:
        locations = [_rounded(p) for p in sources + destinations]
        body = {
            "locations": locations,
            "sources": list(range(len(sources))),
            "destinations": list(range(len(sources), len(locations))),
            "metrics": ["duration", "distance"],
            "units": "m",
        }
        data = self._post("matrix", f"{BASE_URL}/matrix/{PROFILE}", body)
        durations, distances = data.get("durations"), data.get("distances")
        if not durations or not distances:
            raise ProviderError("routing_unavailable", "ORS matrix response has no durations")
        for i, row in enumerate(keys):
            for j, key in enumerate(row):
                sec, meters = durations[i][j], distances[i][j]
                value = None if sec is None or meters is None else (round(sec / 60, 2), float(meters))
                self._remember(self.elements, key, value)
        log.info("ors matrix: %dx%d fetched", len(sources), len(destinations))

    def _post(self, endpoint: str, url: str, body: dict) -> dict:
        """One request plus at most one retry on a transient failure."""
        failure = ""
        for attempt in range(2):
            if attempt:
                time.sleep(RETRY_WAIT_S)
            self.limiters[endpoint].acquire()
            try:
                resp = self.http.post(url, json=body, headers={"Authorization": self._api_key})
            except httpx.HTTPError as e:
                failure = type(e).__name__
                log.warning("ors %s attempt %d failed: %s", endpoint, attempt + 1, failure)
                continue
            if resp.status_code in TRANSIENT_STATUSES:
                failure = f"HTTP {resp.status_code}"
                log.warning("ors %s attempt %d failed: %s", endpoint, attempt + 1, failure)
                continue
            if resp.status_code == 404 or (resp.status_code == 400 and _ors_code(resp) == 2009):
                raise ProviderError("no_route", "ORS found no walking route between the points")
            if resp.status_code != 200:
                raise ProviderError("routing_unavailable", f"ORS {endpoint} HTTP {resp.status_code}")
            return resp.json()
        raise ProviderError("routing_unavailable", f"ORS {endpoint} unavailable: {failure}")

    @staticmethod
    def _remember(cache: dict, key: str, value) -> None:
        if len(cache) >= CACHE_MAX:
            cache.clear()
        cache[key] = value


def _get(value: tuple[float, float] | None, i: int) -> float | None:
    return None if value is None else value[i]


def _ors_code(resp: httpx.Response) -> int | None:
    try:
        return resp.json().get("error", {}).get("code")
    except ValueError:
        return None
