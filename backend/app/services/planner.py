"""Meetup planner (DEV_DOC section 6). Works without any Meta call (fallback rung 2).

Time semantics, for meetup point m and destination e, with A and B leaving together:
    tA = walk(A, m), tB = walk(B, m), tShared = walk(m, e)
    elapsed = max(tA, tB) + tShared, gap = |tA - tB|

The pure functions below take places and travel times as input; `generate_candidates`
is the only one that calls Overpass and ORS.
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.core.geo import haversine_m
from app.core.hours import is_open
from app.models.schemas import Place, TravelMatrix, WalkIntent
from app.providers.overpass import DESTINATION_TYPES

log = logging.getLogger(__name__)

Point = tuple[float, float]  # (lat, lon)

MAX_MEETUPS_QUERIED = 20  # one [A, B] x 20 matrix call
MIN_MEETUPS_KEPT, MAX_MEETUPS_KEPT = 5, 10
MAX_DESTINATIONS = 4  # one kept x 4 matrix call
MEETUP_TIME_SHARE = 0.6  # max(tA, tB) <= duration * 0.6
MAX_GAP_MIN = 5.0
ELAPSED_SLACK_MIN = 3.0
WALK_M_PER_MIN = 83.0  # ORS foot-walking is about 5 km/h
DETOUR_FACTOR = 1.3  # walking distance / straight-line distance, rough
DEDUPE_M = 40.0  # meetup points closer than this are the same spot


@dataclass
class MeetupOption:
    place: Place
    t_a: float
    t_b: float
    d_a: float
    d_b: float

    @property
    def gap(self) -> float:
        return abs(self.t_a - self.t_b)

    @property
    def t_max(self) -> float:
        return max(self.t_a, self.t_b)


@dataclass
class CandidateSet:
    meetups: list[MeetupOption]
    destinations: list[Place]
    shared: TravelMatrix | None  # [meetup][destination]
    stats: dict[str, int] = field(default_factory=dict)


def midpoint(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def meetup_search_radius(a: Point, b: Point) -> int:
    """Wider for origins far apart; 300-1200 m."""
    d = haversine_m(*a, *b)
    return int(min(max(0.35 * d + 250, 300), 1200))


def select_meetup_points(places: list[Place], mid: Point, limit: int, stats: dict) -> list[Place]:
    """Nearest to the midpoint first, one per spot, at most `limit`."""
    ordered = sorted(places, key=lambda p: (haversine_m(*mid, p.lat, p.lon), p.id))
    chosen: list[Place] = []
    for p in ordered:
        if any(haversine_m(p.lat, p.lon, c.lat, c.lon) < DEDUPE_M for c in chosen):
            stats["meetup_duplicate_spot"] = stats.get("meetup_duplicate_spot", 0) + 1
            continue
        if len(chosen) == limit:
            stats["meetup_beyond_query_limit"] = stats.get("meetup_beyond_query_limit", 0) + 1
            continue
        chosen.append(p)
    return chosen


def filter_meetups(
    points: list[Place], times: TravelMatrix, duration_min: int, stats: dict
) -> list[MeetupOption]:
    """times is [A, B] x points. Keep up to MAX_MEETUPS_KEPT with the smallest gap."""
    feasible = []
    for j, p in enumerate(points):
        t_a, t_b = times.durations_min[0][j], times.durations_min[1][j]
        if t_a is None or t_b is None:
            _count(stats, "meetup_no_route")
            continue
        option = MeetupOption(p, t_a, t_b, times.distances_m[0][j], times.distances_m[1][j])
        if option.t_max > duration_min * MEETUP_TIME_SHARE:
            _count(stats, "meetup_over_time_share")
        elif option.gap > MAX_GAP_MIN:
            _count(stats, "meetup_gap_over_max")
        else:
            feasible.append(option)
    feasible.sort(key=lambda o: (o.gap, o.t_max, o.place.id))
    kept = feasible[:MAX_MEETUPS_KEPT]
    if len(feasible) > len(kept):
        stats["meetup_beyond_keep_limit"] = len(feasible) - len(kept)
    return kept


def destination_types(intent: WalkIntent) -> list[str]:
    if intent.endpoint_type in DESTINATION_TYPES:
        return [intent.endpoint_type]
    return [t for t in DESTINATION_TYPES if t != "landmark"]


def remaining_minutes(intent: WalkIntent, meetups: list[MeetupOption]) -> float:
    """Shared-walk time left in the budget after the typical meetup leg."""
    return intent.duration_min - statistics.median(m.t_max for m in meetups)


def destination_search(meetups: list[MeetupOption], target_shared_min: float) -> tuple[Point, int]:
    center = (
        statistics.fmean(m.place.lat for m in meetups),
        statistics.fmean(m.place.lon for m in meetups),
    )
    reach_m = max(target_shared_min, 3) * WALK_M_PER_MIN / DETOUR_FACTOR
    return center, int(min(max(reach_m + 200, 300), 1500))


def select_destinations(
    places: list[Place],
    meetups: list[MeetupOption],
    target_shared_min: float,
    arrive_at: datetime,
    limit: int,
    stats: dict,
) -> list[Place]:
    """Destinations whose estimated shared walk is closest to the time left."""
    meetup_ids = {m.place.id for m in meetups}
    scored = []
    for p in places:
        if p.id in meetup_ids:
            _count(stats, "destination_is_meetup_point")
            continue
        if is_open(p.opening_hours, arrive_at) is False:
            _count(stats, "destination_known_closed")
            continue
        straight = min(haversine_m(m.place.lat, m.place.lon, p.lat, p.lon) for m in meetups)
        est_min = straight * DETOUR_FACTOR / WALK_M_PER_MIN
        scored.append((abs(est_min - target_shared_min), p.id, p))
    scored.sort(key=lambda s: (s[0], s[1]))
    if len(scored) > limit:
        stats["destination_beyond_limit"] = len(scored) - limit
    return [p for _, _, p in scored[:limit]]


def generate_candidates(
    a: Point, b: Point, intent: WalkIntent, overpass, ors, depart_at: datetime
) -> CandidateSet:
    """Step 1 of section 6.2. Raises ProviderError if Overpass or ORS fail."""
    stats: dict[str, int] = {}
    mid = midpoint(a, b)
    radius = meetup_search_radius(a, b)
    fetched = overpass.meetup_candidates(*mid, radius)
    stats["meetup_fetched"] = len(fetched)
    points = select_meetup_points(fetched, mid, MAX_MEETUPS_QUERIED, stats)
    stats["meetup_queried"] = len(points)
    if not points:
        return _done(CandidateSet([], [], None, stats))

    times = ors.matrix([a, b], [(p.lat, p.lon) for p in points])
    kept = filter_meetups(points, times, intent.duration_min, stats)
    stats["meetup_kept"] = len(kept)
    if not kept:
        return _done(CandidateSet([], [], None, stats))

    target = remaining_minutes(intent, kept)
    center, dest_radius = destination_search(kept, target)
    types = destination_types(intent)
    fetched_dest = overpass.destination_candidates(*center, dest_radius, types)
    stats["destination_fetched"] = len(fetched_dest)
    arrive_at = depart_at + timedelta(minutes=intent.duration_min)
    destinations = select_destinations(fetched_dest, kept, target, arrive_at, MAX_DESTINATIONS, stats)
    stats["destination_kept"] = len(destinations)
    if not destinations:
        return _done(CandidateSet(kept, [], None, stats))

    shared = ors.matrix([(m.place.lat, m.place.lon) for m in kept], [(d.lat, d.lon) for d in destinations])
    return _done(CandidateSet(kept, destinations, shared, stats))


def _count(stats: dict, key: str) -> None:
    stats[key] = stats.get(key, 0) + 1


def _done(result: CandidateSet) -> CandidateSet:
    # Counts only: never coordinates.
    log.info("planner candidates: %s", ", ".join(f"{k}={v}" for k, v in sorted(result.stats.items())))
    return result
