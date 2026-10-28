"""Points of interest from OpenStreetMap via the Overpass API.

Overpass is a shared free service, so results are cached on disk for 7 days and a
user-facing request makes at most two attempts: the main server, then one mirror.

Usage policies (wiki.openstreetmap.org/wiki/Overpass_API, checked 2026-10-28):
- overpass-api.de (main, FOSSGIS): for regular use stay under ~100 queries and ~10 MB per
  day across all users; send a User-Agent that identifies the app; no parallel scripts;
  after a 429/406 pause 30 s before the next request (we switch to the mirror instead of
  retrying the main server). The page notes the server is often overloaded.
- maps.mail.ru (mirror, VK Maps, servers in Russia): "Feel free to use our services in any
  project. There are currently no requests limitations". Chosen over
  overpass.private.coffee ("no rate limit in place"), which did not answer a single
  request on 2026-10-28.

What OSM has for meetup points (measured near Washington Square, 700 m, 2026-10-28):
park gates are sparse and unnamed, most subway entrances are unnamed, so meetup
candidates are named parks (their center), park gates (named after their park),
named subway entrances, named plazas and named landmarks.
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

MAX_RADIUS_M = 2000
CACHE_TTL = timedelta(days=7)
USER_AGENT = "StrollCall/0.1 (Meta AI hackathon prototype)"

# Destination categories; WalkIntent.endpoint_type uses the same names.
DESTINATION_FILTERS = {
    "cafe": ['["amenity"="cafe"]'],
    "bookstore": ['["shop"="books"]'],
    "park": ['["leisure"="park"]'],
    "bakery": ['["shop"="bakery"]'],
    "ice_cream": ['["amenity"="ice_cream"]', '["shop"="ice_cream"]'],
    "landmark": [
        '["tourism"~"^(attraction|museum|viewpoint)$"]',
        '["historic"~"^(monument|memorial)$"]',
    ],
}
DESTINATION_TYPES = tuple(DESTINATION_FILTERS)
MEETUP_TYPES = ("park", "park_gate", "subway_entrance", "plaza", "landmark")

# OSM tags kept on a Place for deterministic preference fit.
KEPT_TAGS = (
    "leisure", "amenity", "shop", "tourism", "historic", "place", "highway", "railway",
    "barrier", "entrance", "wheelchair", "outdoor_seating", "garden:type", "natural",
)


def _around(lat: float, lon: float, radius_m: int) -> str:
    return f"(around:{radius_m},{lat:.6f},{lon:.6f})"


def destination_query(lat: float, lon: float, radius_m: int, types: list[str]) -> str:
    around = _around(lat, lon, radius_m)
    lines = [f'  nwr{f}["name"]{around};' for t in types for f in DESTINATION_FILTERS[t]]
    return "[out:json][timeout:25];\n(\n" + "\n".join(lines) + "\n);\nout center tags;"


def meetup_query(lat: float, lon: float, radius_m: int) -> str:
    around = _around(lat, lon, radius_m)
    # foreach prints each park followed by its gates, so a gate can be named after its park.
    return f"""[out:json][timeout:25];
way["leisure"="park"]["name"]{around}->.parks;
foreach.parks->.p(
  .p out ids tags center;
  (node(w.p)["entrance"]; node(w.p)["barrier"="gate"];);
  out tags;
);
(
  nwr["place"="square"]["name"]{around};
  nwr["highway"="pedestrian"]["area"="yes"]["name"]{around};
  node["railway"="subway_entrance"]["name"]{around};
  nwr["tourism"~"^(attraction|viewpoint)$"]["name"]{around};
  nwr["historic"~"^(monument|memorial)$"]["name"]{around};
);
out center tags;"""


def destination_type(tags: dict) -> str:
    if tags.get("leisure") == "park":
        return "park"
    if tags.get("amenity") == "cafe":
        return "cafe"
    if tags.get("shop") == "books":
        return "bookstore"
    if tags.get("shop") == "bakery":
        return "bakery"
    if tags.get("amenity") == "ice_cream" or tags.get("shop") == "ice_cream":
        return "ice_cream"
    return "landmark"


def meetup_type(tags: dict) -> str:
    if tags.get("leisure") == "park":
        return "park"
    if "entrance" in tags or tags.get("barrier") == "gate":
        return "park_gate"
    if tags.get("railway") == "subway_entrance":
        return "subway_entrance"
    if tags.get("place") == "square" or tags.get("highway") == "pedestrian":
        return "plaza"
    return "landmark"


def _place(element: dict, name: str, category: str, fetched_at: datetime) -> Place | None:
    point = element if "lat" in element else element.get("center")
    if not point:
        return None
    tags = element.get("tags") or {}
    return Place(
        id=f"{element['type']}/{element['id']}",
        name=name,
        lat=point["lat"],
        lon=point["lon"],
        category=category,
        opening_hours=tags.get("opening_hours"),
        tags={k: tags[k] for k in KEPT_TAGS if k in tags},
        fetched_at=fetched_at,
    )


def parse_destinations(elements: list[dict], fetched_at: datetime) -> list[Place]:
    places = []
    for e in elements:
        tags = e.get("tags") or {}
        if tags.get("name"):
            places.append(_place(e, tags["name"], destination_type(tags), fetched_at))
    return [p for p in places if p]


def parse_meetups(elements: list[dict], fetched_at: datetime) -> list[Place]:
    places = []
    park_name = None
    for e in elements:
        tags = e.get("tags") or {}
        kind = meetup_type(tags)
        if kind == "park":
            park_name = tags.get("name")
        if kind == "park_gate":
            name = tags.get("name") or (f"{park_name} gate" if park_name else None)
        else:
            name = tags.get("name")
        if name:
            places.append(_place(e, name, kind, fetched_at))
    return [p for p in places if p]


class DiskCache:
    """One JSON file per query under <root>/overpass/. ttl=None never expires (fixtures)."""

    def __init__(self, root: Path, ttl: timedelta | None = CACHE_TTL):
        self.root = root / "overpass"
        self.ttl = ttl

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
        if self.ttl is not None and datetime.now(timezone.utc) - fetched_at > self.ttl:
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


def meetup_key(lat: float, lon: float, radius_m: int) -> tuple:
    return ("meetup", coord_key(lat, lon, 3), radius_m)


def destination_key(lat: float, lon: float, radius_m: int, types: list[str]) -> tuple:
    return ("destination", coord_key(lat, lon, 3), radius_m, sorted(types))


def _check_types(types: list[str] | None) -> list[str]:
    types = sorted(set(types or DESTINATION_TYPES))
    if unknown := set(types) - set(DESTINATION_TYPES):
        raise ValueError(f"unknown destination types: {sorted(unknown)}")
    return types


class OverpassProvider:
    name = "overpass"

    def __init__(self, settings: Settings | None = None, http: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self.http = http or httpx.Client(
            timeout=self.settings.overpass_timeout_s, headers={"User-Agent": USER_AGENT}
        )
        self.cache = DiskCache(self.settings.cache_dir)

    def meetup_candidates(self, lat: float, lon: float, radius_m: float) -> list[Place]:
        radius = int(min(radius_m, MAX_RADIUS_M))
        return self._cached(
            meetup_key(lat, lon, radius), meetup_query(lat, lon, radius), parse_meetups
        )

    def destination_candidates(
        self, lat: float, lon: float, radius_m: float, types: list[str] | None = None
    ) -> list[Place]:
        types = _check_types(types)
        radius = int(min(radius_m, MAX_RADIUS_M))
        return self._cached(
            destination_key(lat, lon, radius, types),
            destination_query(lat, lon, radius, types),
            parse_destinations,
        )

    # Day 1 name, kept for the smoke test.
    places_near = destination_candidates

    def _cached(self, key: tuple, query: str, parse) -> list[Place]:
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        fetched_at = datetime.now(timezone.utc)
        unique: dict[str, Place] = {}
        for place in parse(self._fetch(query), fetched_at):
            unique.setdefault(place.id, place)
        result = sorted(unique.values(), key=lambda p: (p.category, p.name, p.id))
        log.info("overpass %s: %d places, radius %d m", key[0], len(result), key[2])
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
                log.warning("overpass server failed (%s); trying the next one", failures[-1])
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
