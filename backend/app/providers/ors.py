"""Walking legs from openrouteservice (foot-walking profile).

Legs are cached in memory by rounded coordinates (4 decimals, about 11 m), and the
rounded points are what we send, so a cached leg is exactly the leg ORS returned.
"""

import logging

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ProviderError
from app.core.geo import coord_key
from app.models.schemas import RouteLeg

log = logging.getLogger(__name__)

ORS_URL = "https://api.openrouteservice.org/v2/directions/{profile}/geojson"
PROFILE = "foot-walking"
CACHE_MAX = 2048


def route_key(start: tuple[float, float], end: tuple[float, float]) -> str:
    return f"{coord_key(*start)}|{coord_key(*end)}"


class ORSProvider:
    name = "ors"

    def __init__(self, settings: Settings | None = None, http: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self._api_key = self.settings.ors_api_key.get_secret_value()
        if not self._api_key:
            raise ProviderError("routing_unavailable", "ORS_API_KEY is not set")
        self.http = http or httpx.Client(timeout=20.0)
        self._cache: dict[str, RouteLeg] = {}

    def walk(self, start: tuple[float, float], end: tuple[float, float]) -> RouteLeg:
        """start and end are (lat, lon)."""
        key = route_key(start, end)
        if key in self._cache:
            return self._cache[key]

        (lat1, lon1), (lat2, lon2) = (round(c, 4) for c in start), (round(c, 4) for c in end)
        body = {"coordinates": [[lon1, lat1], [lon2, lat2]]}
        try:
            resp = self.http.post(
                ORS_URL.format(profile=PROFILE),
                json=body,
                headers={"Authorization": self._api_key},
            )
        except httpx.HTTPError as e:
            raise ProviderError("routing_unavailable", f"ORS {type(e).__name__}") from e

        if resp.status_code == 404 or (resp.status_code == 400 and _ors_code(resp) == 2009):
            raise ProviderError("no_route", "ORS found no walking route between the points")
        if resp.status_code != 200:
            raise ProviderError("routing_unavailable", f"ORS HTTP {resp.status_code}")

        features = resp.json().get("features") or []
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

        if len(self._cache) >= CACHE_MAX:
            self._cache.clear()
        self._cache[key] = leg
        return leg


def _ors_code(resp: httpx.Response) -> int | None:
    try:
        return resp.json().get("error", {}).get("code")
    except ValueError:
        return None
