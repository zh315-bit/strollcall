"""Points of interest from OpenStreetMap via the Overpass API.

Overpass is a shared free service: queries are small, time-limited and cached, and a
failure is reported as an error (no retry loop).
"""

import logging
import time

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ProviderError
from app.core.geo import coord_key
from app.models.schemas import Place

log = logging.getLogger(__name__)

CATEGORIES = ("park", "cafe", "bookstore", "landmark")
MAX_RADIUS_M = 2000
CACHE_TTL_S = 600
CACHE_MAX = 256
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


def to_place(element: dict) -> Place | None:
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
    )


class OverpassProvider:
    name = "overpass"

    def __init__(self, settings: Settings | None = None, http: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self.http = http or httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT})
        self._cache: dict[tuple, tuple[float, list[Place]]] = {}

    def places_near(
        self, lat: float, lon: float, radius_m: float, categories: list[str] | None = None
    ) -> list[Place]:
        cats = sorted(categories or CATEGORIES)
        if unknown := set(cats) - set(CATEGORIES):
            raise ValueError(f"unknown categories: {sorted(unknown)}")
        radius = int(min(radius_m, MAX_RADIUS_M))
        key = (coord_key(lat, lon, 3), radius, tuple(cats))
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1]

        try:
            resp = self.http.post(
                self.settings.overpass_url, data={"data": build_query(lat, lon, radius, cats)}
            )
        except httpx.HTTPError as e:
            raise ProviderError("places_unavailable", f"Overpass {type(e).__name__}") from e
        if resp.status_code != 200:
            raise ProviderError("places_unavailable", f"Overpass HTTP {resp.status_code}")

        places: dict[str, Place] = {}
        for element in resp.json().get("elements", []):
            place = to_place(element)
            if place:
                places.setdefault(place.id, place)
        result = sorted(places.values(), key=lambda p: (p.category, p.name, p.id))
        log.info("overpass: %d places, radius %d m, categories %s", len(result), radius, cats)

        if len(self._cache) >= CACHE_MAX:
            self._cache.clear()
        self._cache[key] = (time.monotonic(), result)
        return result
