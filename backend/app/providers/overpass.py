"""Points of interest from OpenStreetMap via the Overpass API, cached as fixed tiles.

The map is cut into fixed tiles of about 1.1 x 1.1 km. Each tile holds every meetup place
or every destination place (all types) inside it, cached on disk for 7 days. A query for
"places within r of a point" loads the tiles the circle touches and filters them locally,
so any origins in a neighborhood warmed by scripts/warm_cache.py are served from cache.
Missing tiles are fetched in one bounding-box request: the main server once, then one
mirror. No other retries.

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

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ProviderError
from app.core.geo import haversine_m
from app.models.schemas import Place

log = logging.getLogger(__name__)

MAX_RADIUS_M = 2000
CACHE_TTL = timedelta(days=7)
TILE_LAT, TILE_LON = 0.01, 0.013  # about 1.1 x 1.1 km in New York
KINDS = ("meetup", "destination")
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


Tile = tuple[int, int]
BBox = tuple[float, float, float, float]  # south, west, north, east


def tile_of(lat: float, lon: float) -> Tile:
    return (math.floor(lat / TILE_LAT), math.floor(lon / TILE_LON))


def tiles_for_circle(lat: float, lon: float, radius_m: float) -> list[Tile]:
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * math.cos(math.radians(lat)))
    (i0, j0), (i1, j1) = tile_of(lat - dlat, lon - dlon), tile_of(lat + dlat, lon + dlon)
    return [(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]


def tiles_in_box(south: float, west: float, north: float, east: float) -> list[Tile]:
    (i0, j0), (i1, j1) = tile_of(south, west), tile_of(north, east)
    return [(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]


def batches(tiles: list[Tile], size: int = 2) -> list[list[Tile]]:
    """Group tiles into size x size blocks, so each fetch stays a small Overpass query."""
    groups: dict[Tile, list[Tile]] = {}
    for i, j in sorted(tiles):
        groups.setdefault((i // size, j // size), []).append((i, j))
    return [groups[k] for k in sorted(groups)]


def tiles_bbox(tiles: list[Tile]) -> tuple[BBox, list[Tile]]:
    """Bounding box of the tiles, and every tile inside that box."""
    i0, i1 = min(t[0] for t in tiles), max(t[0] for t in tiles)
    j0, j1 = min(t[1] for t in tiles), max(t[1] for t in tiles)
    bbox = (i0 * TILE_LAT, j0 * TILE_LON, (i1 + 1) * TILE_LAT, (j1 + 1) * TILE_LON)
    return bbox, [(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]


def _bbox(b: BBox) -> str:
    return f"({b[0]:.4f},{b[1]:.4f},{b[2]:.4f},{b[3]:.4f})"


def destination_query(bbox: BBox) -> str:
    box = _bbox(bbox)
    lines = [f'  nwr{f}["name"]{box};' for fs in DESTINATION_FILTERS.values() for f in fs]
    return "[out:json][timeout:25];\n(\n" + "\n".join(lines) + "\n);\nout center tags;"


def meetup_query(bbox: BBox) -> str:
    box = _bbox(bbox)
    # foreach prints each park followed by its gates, so a gate can be named after its park.
    # Gates use plain `out;` because `out tags;` would drop node coordinates.
    return f"""[out:json][timeout:25];
way["leisure"="park"]["name"]{box}->.parks;
foreach.parks->.p(
  .p out ids tags center;
  (node(w.p)["entrance"]; node(w.p)["barrier"="gate"];);
  out;
);
(
  nwr["place"="square"]["name"]{box};
  nwr["highway"="pedestrian"]["area"="yes"]["name"]{box};
  node["railway"="subway_entrance"]["name"]{box};
  nwr["tourism"~"^(attraction|viewpoint)$"]["name"]{box};
  nwr["historic"~"^(monument|memorial)$"]["name"]{box};
);
out center tags;"""


QUERIES = {"meetup": (meetup_query, parse_meetups), "destination": (destination_query, parse_destinations)}


class TileCache:
    """One JSON file per (kind, tile) under <root>/overpass_tiles/. ttl=None never expires."""

    def __init__(self, root: Path, ttl: timedelta | None = CACHE_TTL):
        self.root = root / "overpass_tiles"
        self.ttl = ttl

    def _path(self, kind: str, tile: Tile) -> Path:
        return self.root / f"{kind}_{tile[0]}_{tile[1]}.json"

    def get(self, kind: str, tile: Tile) -> list[Place] | None:
        path = self._path(kind, tile)
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

    def put(self, kind: str, tile: Tile, places: list[Place], fetched_at: datetime) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        data = {
            "kind": kind,
            "tile": list(tile),
            "fetched_at": fetched_at.isoformat(),
            "places": [p.model_dump(mode="json") for p in places],
        }
        self._path(kind, tile).write_text(json.dumps(data))


def _check_types(types: list[str] | None) -> list[str]:
    types = sorted(set(types or DESTINATION_TYPES))
    if unknown := set(types) - set(DESTINATION_TYPES):
        raise ValueError(f"unknown destination types: {sorted(unknown)}")
    return types


def within(places: list[Place], lat: float, lon: float, radius_m: float) -> list[Place]:
    unique = {p.id: p for p in places if haversine_m(lat, lon, p.lat, p.lon) <= radius_m}
    return sorted(unique.values(), key=lambda p: (p.category, p.name, p.id))


class TiledPlaces:
    """Shared query logic over a TileCache; `fetch` is None for replay-only (mock) use."""

    def __init__(self, cache: TileCache, fetch=None):
        self.cache = cache
        self.fetch = fetch

    def meetup_candidates(self, lat: float, lon: float, radius_m: float) -> list[Place]:
        radius = min(radius_m, MAX_RADIUS_M)
        return within(self._load("meetup", tiles_for_circle(lat, lon, radius)), lat, lon, radius)

    def destination_candidates(
        self, lat: float, lon: float, radius_m: float, types: list[str] | None = None
    ) -> list[Place]:
        types = _check_types(types)
        radius = min(radius_m, MAX_RADIUS_M)
        places = self._load("destination", tiles_for_circle(lat, lon, radius))
        return within([p for p in places if p.category in types], lat, lon, radius)

    # Day 1 name, kept for the smoke test.
    places_near = destination_candidates

    def _load(self, kind: str, tiles: list[Tile]) -> list[Place]:
        places, missing = [], []
        for tile in tiles:
            cached = self.cache.get(kind, tile)
            if cached is None:
                missing.append(tile)
            else:
                places.extend(cached)
        if missing:
            if self.fetch is None:
                raise ProviderError("places_unavailable", "no captured Overpass tile in mock mode")
            for fetched in self.fetch_tiles(kind, missing).values():
                places.extend(fetched)
        return places

    def missing_tiles(self, kind: str, tiles: list[Tile]) -> list[Tile]:
        return [t for t in tiles if self.cache.get(kind, t) is None]

    def fetch_tiles(self, kind: str, tiles: list[Tile]) -> dict[Tile, list[Place]]:
        """One request for the bounding box of `tiles`; caches every tile in that box."""
        bbox, box_tiles = tiles_bbox(tiles)
        build_query, parse = QUERIES[kind]
        fetched_at = datetime.now(timezone.utc)
        by_tile: dict[Tile, list[Place]] = {t: [] for t in box_tiles}
        for place in parse(self.fetch(build_query(bbox)), fetched_at):
            tile = tile_of(place.lat, place.lon)
            if tile in by_tile:  # parks reaching into the box but centered outside belong elsewhere
                by_tile[tile].append(place)
        for tile, places in by_tile.items():
            self.cache.put(kind, tile, places, fetched_at)
        log.info("overpass %s: fetched %d tiles, %d places", kind, len(by_tile),
                 sum(len(p) for p in by_tile.values()))
        return {t: by_tile[t] for t in tiles}


class OverpassProvider(TiledPlaces):
    name = "overpass"

    def __init__(self, settings: Settings | None = None, http: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self.http = http or httpx.Client(
            timeout=self.settings.overpass_timeout_s, headers={"User-Agent": USER_AGENT}
        )
        super().__init__(TileCache(self.settings.cache_dir), fetch=self._fetch)

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
