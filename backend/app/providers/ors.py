"""Walking times from openrouteservice (foot-walking profile): directions and matrix.

Points are rounded to 4 decimals (about 11 m) before they are sent, and results are
cached in memory under those rounded points, so a cached value is exactly what ORS
returned for them. Limits: 40 requests per minute each for directions and matrix and at
most 3,500 matrix elements per request (openrouteservice.org/plans). Daily quotas are
per key: on 2026-10-28 our key reported x-ratelimit-limit 200 for directions, and the
matrix endpoint answered 403 "Quota exceeded" after a few dozen calls, so the daily
budget is far smaller than the published 2,000 / 500.
"""

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.core.config import Settings, forbid_live_client_in_tests, get_settings
from app.core.errors import ProviderError
from app.core.geo import coord_key
from app.models.db import db
from app.models.schemas import RouteLeg, TravelMatrix

log = logging.getLogger(__name__)

BASE_URL = "https://api.openrouteservice.org/v2"
PROFILE = "foot-walking"
CACHE_MAX = 20_000
MAX_MATRIX_ELEMENTS = 3500
RATE_LIMIT_PER_MIN = 40
TRANSIENT_STATUSES = (429, 500, 502, 503, 504)
RETRY_WAIT_S = 2.0
QUOTA_RECHECK = timedelta(hours=1)  # after a 403 with no reset header, probe again after this

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


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ORSStore:
    """Persistent ORS state in SQLite: results cache, request log and last known quota."""

    def __init__(self, db_path: Path, cache_days: int):
        self.db_path = db_path
        self.ttl = timedelta(days=cache_days)

    def cached(self, kind: str, keys: list[str]) -> dict[str, object]:
        if not keys:
            return {}
        cutoff = (_now() - self.ttl).isoformat()
        found = {}
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            rows = db(self.db_path).query(
                f"SELECT key, value FROM ors_cache WHERE kind = ? AND fetched_at >= ? "
                f"AND key IN ({','.join('?' * len(chunk))})",
                [kind, cutoff, *chunk],
            )
            found.update({r["key"]: json.loads(r["value"]) for r in rows})
        return found

    def store(self, kind: str, items: dict[str, object]) -> None:
        now = _now().isoformat()
        db(self.db_path).run_many(
            "INSERT INTO ors_cache (kind, key, value, fetched_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (kind, key) DO UPDATE SET value = excluded.value, fetched_at = excluded.fetched_at",
            [(kind, k, json.dumps(v), now) for k, v in items.items()],
        )

    def log_request(self, endpoint: str, caller: str, status: int) -> None:
        db(self.db_path).run(
            "INSERT INTO ors_requests (ts, endpoint, caller, status) VALUES (?, ?, ?, ?)",
            (_now().isoformat(), endpoint, caller, status),
        )

    def requests_24h(self, endpoint: str | None = None) -> int:
        since = (_now() - timedelta(hours=24)).isoformat()
        sql, args = "SELECT COUNT(*) AS n FROM ors_requests WHERE ts >= ?", [since]
        if endpoint:
            sql, args = sql + " AND endpoint = ?", args + [endpoint]
        return int(db(self.db_path).query(sql, args)[0]["n"])

    def usage_24h(self) -> dict[str, dict[str, int]]:
        """{endpoint: {caller: count}} over the last 24 h."""
        since = (_now() - timedelta(hours=24)).isoformat()
        rows = db(self.db_path).query(
            "SELECT endpoint, caller, COUNT(*) AS n FROM ors_requests WHERE ts >= ? GROUP BY endpoint, caller",
            (since,),
        )
        usage: dict[str, dict[str, int]] = {}
        for r in rows:
            usage.setdefault(r["endpoint"], {})[r["caller"]] = r["n"]
        return usage

    def set_quota(self, endpoint: str, remaining: int, reset_at: datetime) -> None:
        db(self.db_path).run(
            "INSERT INTO ors_quota (endpoint, remaining, reset_at) VALUES (?, ?, ?) "
            "ON CONFLICT (endpoint) DO UPDATE SET remaining = excluded.remaining, reset_at = excluded.reset_at",
            (endpoint, remaining, reset_at.isoformat()),
        )

    def quota(self, endpoint: str) -> tuple[int, datetime] | None:
        rows = db(self.db_path).query("SELECT remaining, reset_at FROM ors_quota WHERE endpoint = ?", (endpoint,))
        row = rows[0] if rows else None
        if not row or row["reset_at"] is None:
            return None
        return row["remaining"], datetime.fromisoformat(row["reset_at"])


class ORSProvider:
    name = "ors"

    def __init__(
        self, settings: Settings | None = None, http: httpx.Client | None = None,
        disk_cache: bool = True,
    ):
        """disk_cache=False skips cache reads (benchmark --cold); results are still stored."""
        self.settings = settings or get_settings()
        self.disk_cache = disk_cache
        self._api_key = self.settings.ors_api_key.get_secret_value()
        if not self._api_key:
            raise ProviderError("routing_unavailable", "ORS_API_KEY is not set")
        if http is None:
            forbid_live_client_in_tests("ORSProvider")
        self.http = http or httpx.Client(timeout=20.0)
        self.store = ORSStore(self.settings.db_path, self.settings.ors_cache_days)
        self.caps = {
            "matrix": self.settings.ors_matrix_soft_cap,
            "directions": self.settings.ors_directions_soft_cap,
        }
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
        stored = self.store.cached("leg", [key]) if self.disk_cache else {}
        if key in stored:
            self.legs[key] = RouteLeg.model_validate(stored[key])
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
        self.store.store("leg", {key: leg.model_dump()})
        return leg

    def matrix(self, sources: list[Point], destinations: list[Point],
               limit_min: float | None = None) -> TravelMatrix:  # limit_min: local engine only
        """Walking minutes and meters from every source to every destination.

        An entry is None when ORS found no route between that pair.
        """
        if not sources or not destinations:
            raise ValueError("matrix needs at least one source and one destination")
        if len(sources) * len(destinations) > MAX_MATRIX_ELEMENTS:
            raise ValueError("matrix request exceeds the ORS element limit")

        keys = [[route_key(s, d) for d in destinations] for s in sources]
        missing = [k for row in keys for k in row if k not in self.elements]
        for k, v in (self.store.cached("element", missing) if self.disk_cache else {}).items():
            self.elements[k] = None if v is None else tuple(v)
        rows = [i for i, row in enumerate(keys) if any(k not in self.elements for k in row)]
        cols = [j for j in range(len(destinations)) if any(keys[i][j] not in self.elements for i in rows)]
        if rows:
            # Ask only for the sources and destinations that still have a gap.
            self._fetch_matrix(
                [sources[i] for i in rows],
                [destinations[j] for j in cols],
                [[keys[i][j] for j in cols] for i in rows],
            )
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
        self.store.store("element", {k: self.elements[k] for row in keys for k in row})
        log.info("ors matrix: %dx%d fetched", len(sources), len(destinations))

    def _post(self, endpoint: str, url: str, body: dict) -> dict:
        """One request plus at most one retry on a transient failure."""
        failure = ""
        for attempt in range(2):
            if attempt:
                time.sleep(RETRY_WAIT_S)
            self._check_budget(endpoint)
            self.limiters[endpoint].acquire()
            try:
                resp = self.http.post(url, json=body, headers={"Authorization": self._api_key})
            except httpx.HTTPError as e:
                self.store.log_request(endpoint, self.settings.strollcall_caller, 0)
                failure = type(e).__name__
                log.warning("ors %s attempt %d failed: %s", endpoint, attempt + 1, failure)
                continue
            self.store.log_request(endpoint, self.settings.strollcall_caller, resp.status_code)
            self._read_quota(endpoint, resp)
            if resp.status_code == 403:
                # Daily quota used up (the 403 carries no reset header): pause live calls.
                self.store.set_quota(endpoint, 0, _now() + QUOTA_RECHECK)
                raise ProviderError("routing_unavailable", f"ORS {endpoint} daily quota exceeded")
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

    def _check_budget(self, endpoint: str) -> None:
        """Our own stop before ORS stops us: soft cap and the last quota ORS reported."""
        used = self.store.requests_24h(endpoint)
        if used >= self.caps[endpoint]:
            log.warning("ors %s: soft cap reached (%d in 24 h, cap %d); live calls stopped",
                        endpoint, used, self.caps[endpoint])
            raise ProviderError(
                "routing_unavailable",
                f"ORS {endpoint} soft cap reached ({used} requests in 24 h, cap {self.caps[endpoint]})",
            )
        quota = self.store.quota(endpoint)
        if quota and quota[0] <= self.settings.ors_quota_reserve and _now() < quota[1]:
            log.warning("ors %s: quota nearly used (%d left until %s); live calls stopped",
                        endpoint, quota[0], quota[1].isoformat(timespec="minutes"))
            raise ProviderError(
                "routing_unavailable",
                f"ORS {endpoint} quota exhausted until {quota[1].isoformat(timespec='minutes')} UTC",
            )

    def _read_quota(self, endpoint: str, resp: httpx.Response) -> None:
        remaining, reset = resp.headers.get("x-ratelimit-remaining"), resp.headers.get("x-ratelimit-reset")
        if remaining is not None and reset is not None:
            try:
                reset_at = datetime.fromtimestamp(int(reset), tz=timezone.utc)
                self.store.set_quota(endpoint, int(remaining), reset_at)
            except ValueError:
                pass

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
