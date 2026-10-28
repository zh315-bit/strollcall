"""Points of interest from OpenStreetMap via the Overpass API.

Overpass is a shared free service, so results are cached on disk for 7 days and a
user-facing request makes at most two attempts: the main server, then one mirror.

Usage policies (wiki.openstreetmap.org/wiki/Overpass_API, checked 2026-10-28):
- overpass-api.de (main, FOSSGIS): for regular use stay under ~100 queries and ~10 MB per
  day across all users; send a User-Agent that identifies the app; no parallel scripts;
  after a 429/406 pause 30 s before the next request (we switch to the mirror instead of
  retrying the main server). The page notes the server is often overloaded.
- overpass.private.coffee (mirror, formerly overpass.kumi.systems): "Feel free to use our
  service in any project, there is no rate limit in place"; asks to be notified in
  advance for large-scale use.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ProviderError
from app.core.geo import coord_key
from app.models.schemas import Place

log = logging.getLogger(__name__)

CATEGORIES = ("park", "cafe", "bookstore", "landmark")
MAX_RADIUS_M = 2000
CACHE_TTL = timedelta(days=7)
USER_AGENT = "StrollCall/0.1 (Meta AI hackathon prototype)"

FILTERS = {
    "park": ['["leisure"="park"]'],
    "cafe": ['["amenity"="cafe"]'],
    "bookstore": ['["shop"="books"]'],
    "landmark": [
        '["tourism"~"^(attraction|museum|viewpoint)$"]',
        '["historic"~"^(monument|memorial)$"]',
    ],
}


def build_query(lat: float, lon: float, radius_m: int, categories: list[str]) -> str:
    around = f"(around:{radius_m},{lat:.6f},{lon:.6f})"
    lines = [f'  nwr{f}["name"]{around};' for c in categories for f in FILTERS[c]]
    return "[out:json][timeout:25];\n(\n" + "\n".join(lines) + "\n);\nout center tags;"


def category_of(tags: dict) -> str:
    if tags.get("leisure") == "park":
        return "park"
    if tags.get("amenity") == "cafe":
        return "cafe"
    if tags.get("shop") == "books":
        return "bookstore"
    return "landmark"


def to_place(element: dict, fetched_at: datetime) -> Place | None:
    tags = element.get("tags") or {}
    name = tags.get("name")
    point = element if "lat" in element else element.get("center")
    if not name or not point:
        return None
    return Place(
        id=f"{element['type']}/{element['id']}",
        name=name,
        lat=point["lat"],
        lon=point["lon"],
        category=category_of(tags),
        opening_hours=tags.get("opening_hours"),
        fetched_at=fetched_at,
    )


class DiskCache:
    """One JSON file per query under cache/overpass/, valid for CACHE_TTL."""

    def __init__(self, root: Path):
        self.root = root / "overpass"

    def _path(self, key: tuple) -> Path:
        digest = hashlib.sha1(json.dumps(key).encode()).hexdigest()[:20]
        return self.root / f"{digest}.json"

    def get(self, key: tuple) -> list[Place] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            fetched_at = datetime.fromisoformat(data["fetched_at"])
        except (ValueError, KeyError):
            return None
        if datetime.now(timezone.utc) - fetched_at > CACHE_TTL:
            return None
        return [Place.model_validate(p) for p in data["places"]]

    def put(self, key: tuple, places: list[Place], fetched_at: datetime) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        data = {
            "key": list(key),
            "fetched_at": fetched_at.isoformat(),
            "places": [p.model_dump(mode="json") for p in places],
        }
        self._path(key).write_text(json.dumps(data))


class OverpassProvider:
    name = "overpass"

    def __init__(self, settings: Settings | None = None, http: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self.http = http or httpx.Client(
            timeout=self.settings.overpass_timeout_s, headers={"User-Agent": USER_AGENT}
        )
        self.cache = DiskCache(self.settings.cache_dir)

    def places_near(
        self, lat: float, lon: float, radius_m: float, categories: list[str] | None = None
    ) -> list[Place]:
        cats = sorted(categories or CATEGORIES)
        if unknown := set(cats) - set(CATEGORIES):
            raise ValueError(f"unknown categories: {sorted(unknown)}")
        radius = int(min(radius_m, MAX_RADIUS_M))
        key = ("places", coord_key(lat, lon, 3), radius, cats)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        elements = self._fetch(build_query(lat, lon, radius, cats))
        fetched_at = datetime.now(timezone.utc)
        places: dict[str, Place] = {}
        for element in elements:
            place = to_place(element, fetched_at)
            if place:
                places.setdefault(place.id, place)
        result = sorted(places.values(), key=lambda p: (p.category, p.name, p.id))
        log.info("overpass: %d places, radius %d m, categories %s", len(result), radius, cats)
        self.cache.put(key, result, fetched_at)
        return result

    def _fetch(self, query: str) -> list[dict]:
        """Main server once, then the mirror once. No other retries."""
        failures = []
        for url in (self.settings.overpass_url, self.settings.overpass_mirror_url):
            if not url:
                continue
            try:
                resp = self.http.post(url, data={"data": query})
            except httpx.HTTPError as e:
                failures.append(type(e).__name__)
                continue
            if resp.status_code == 200:
                try:
                    return resp.json().get("elements", [])
                except ValueError:
                    failures.append("invalid JSON")
                    continue
            failures.append(f"HTTP {resp.status_code}")
            log.warning("overpass server failed (%s); trying the next one", failures[-1])
        raise ProviderError("places_unavailable", "Overpass unavailable: " + ", ".join(failures))
