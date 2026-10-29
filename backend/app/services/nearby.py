"""'Near you' highlights for a start point, and the places a walker asked to pass by.

Only local data: the place snapshot (OpenStreetMap), the route POIs, the walking graph and the
intros written ahead of time (frontend/data/poi_intros.json). No Meta call. The start point is used
once and neither stored nor logged. Nothing is described beyond the data: name, category, walking
minutes, opening hours with source and date, and a sourced intro where one exists.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.core.config import ROOT_DIR
from app.core.geo import haversine_m
from app.core.hours import is_open

log = logging.getLogger(__name__)

NYC = ZoneInfo("America/New_York")
NEAR_MIN = 15.0  # "within about 15 minutes' walk"
SEARCH_M = 1100.0  # straight-line prefilter (15 min at 80 m/min, minus a little for street detours)
PER_KIND = 8  # nearest candidates of each kind sent to the walking graph
LANDMARK_KINDS = ("landmark", "historic site", "memorial", "artwork")
INTROS_PATH = ROOT_DIR / "frontend" / "data" / "poi_intros.json"


@lru_cache(maxsize=1)
def intro_ids() -> frozenset[str]:
    try:
        return frozenset(json.loads(INTROS_PATH.read_text()).get("intros", {}))
    except (OSError, ValueError):
        return frozenset()


class Highlight(BaseModel):
    id: str
    name: str
    kind: str  # park / cafe / landmark (what made it a highlight)
    category: str  # shown: park, cafe, historic site, artwork, memorial, landmark
    lat: float  # the point walked to (for a park: its edge nearest the start)
    lon: float
    walk_min: int
    opening_hours: str | None = None
    hours_source: str | None = None  # "OpenStreetMap, as of 2026-10-28"
    open_now: bool | None = None
    has_intro: bool = False  # the page shows the sourced intro from poi_intros.json


@dataclass
class Spot:
    id: str
    name: str
    kind: str
    category: str
    pts: list = field(default_factory=list)  # [[lat, lon], ...]
    opening_hours: str | None = None
    fetched_at: str | None = None

    def nearest(self, p) -> tuple[float, float]:
        return min(((float(a), float(b)) for a, b in self.pts), key=lambda q: haversine_m(*p, *q))


def _spots(origin, places, pois) -> list[Spot]:
    """Named parks and landmark-like places (route POIs) and cafes (snapshot) near the origin."""
    out: list[Spot] = []
    for p in (pois.pois if pois else []):
        if p["category"] == "park" or p["category"] in LANDMARK_KINDS:
            if haversine_m(*origin, p["lat"], p["lon"]) <= SEARCH_M or \
               any(haversine_m(*origin, a, b) <= SEARCH_M for a, b in p["pts"][::4]):
                kind = "park" if p["category"] == "park" else "landmark"
                out.append(Spot(p["id"], p["name"], kind, p["category"], p["pts"]))
    snap = getattr(places, "snapshot", None)
    if snap is not None:
        for c in snap.destination.within(*origin, SEARCH_M):
            if c.category == "cafe":
                out.append(Spot(c.id, c.name, "cafe", "cafe", [[c.lat, c.lon]], c.opening_hours, c.fetched_at))
    return out


def highlights(origin: tuple[float, float], now: datetime | None = None) -> list[Highlight]:
    """2-3 places within about 15 minutes' walk, for variety: a park, a cafe open now, a landmark
    (preferring one with a sourced intro). Fewer when the area has fewer."""
    from app.providers import get_places, get_routing

    routing, places = get_routing(), get_places()
    if not hasattr(routing, "graph"):
        return []  # only on the local walking graph: no external routing for a browse
    now = now or datetime.now(NYC)
    intros = intro_ids()
    spots = _spots(origin, places, getattr(routing, "pois", None))

    by_kind: dict[str, list[Spot]] = {"park": [], "cafe": [], "landmark": []}
    for s in spots:
        if s.kind == "cafe" and is_open(s.opening_hours, now) is not True:
            continue  # "one cafe open now": only when OSM hours say so
        by_kind[s.kind].append(s)
    picks: list[Highlight] = []
    for kind, group in by_kind.items():
        # Nearest first; a landmark with a sourced intro beats one without.
        group.sort(key=lambda s: ((kind == "landmark" and s.id not in intros), haversine_m(*origin, *s.nearest(origin))))
        group = group[:PER_KIND]
        if not group:
            continue
        targets = [s.nearest(origin) for s in group]
        times = routing.matrix([origin], targets, limit_min=NEAR_MIN).durations_min[0]
        for s, t, (lat, lon) in zip(group, times, targets):
            if t is None or t > NEAR_MIN:
                continue
            picks.append(Highlight(
                id=s.id, name=s.name, kind=kind, category=s.category, lat=lat, lon=lon, walk_min=max(1, round(t)),
                opening_hours=s.opening_hours,
                hours_source=f"OpenStreetMap, as of {str(s.fetched_at)[:10]}" if s.opening_hours and s.fetched_at else None,
                open_now=is_open(s.opening_hours, now) if s.opening_hours else None,
                has_intro=s.id in intros,
            ))
            break
    log.info("nearby: %d highlights", len(picks))  # counts only, never the start point
    return picks


@dataclass
class PassBy:
    """A place the walker asked to pass by: a soft preference for the planner."""
    id: str
    name: str
    pts: list  # [[lat, lon], ...] (a park's outline samples, or one point)


def resolve_pass_by(ids: list[str]) -> list[PassBy]:
    """Known places only, by id; names and positions come from our data, never from the request."""
    from app.providers import get_places, get_routing

    wanted = list(dict.fromkeys(ids))[:3]
    if not wanted:
        return []
    found: dict[str, PassBy] = {}
    pois = getattr(get_routing(), "pois", None)
    for p in (pois.pois if pois else []):
        if p["id"] in wanted:
            found[p["id"]] = PassBy(p["id"], p["name"], p["pts"])
    snap = getattr(get_places(), "snapshot", None)
    if snap is not None:
        for index in (snap.meetup, snap.destination):
            for c in index.places:
                if c.id in wanted and c.id not in found:
                    found[c.id] = PassBy(c.id, c.name, [[c.lat, c.lon]])
    return [found[i] for i in wanted if i in found]
