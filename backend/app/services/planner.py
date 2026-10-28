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

from pydantic import BaseModel

from app.core.errors import ProviderError
from app.core.geo import haversine_m
from app.core.hours import is_open
from app.models.schemas import MeetupCandidate, Place, RouteLeg, TravelMatrix, WalkIntent
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


# --- Step 2: hard constraints and score (section 6.2 step 6, section 6.3) ---

# Vibe word -> test on a place, using only OSM category and tags. Unknown vibes are ignored.
VIBE_TESTS = {
    "green": lambda p: p.category in ("park", "park_gate") or "garden:type" in p.tags or "natural" in p.tags,
    "shady": lambda p: p.category in ("park", "park_gate"),
    "quiet": lambda p: p.category in ("park", "park_gate", "bookstore"),
    "lively": lambda p: p.category in ("cafe", "plaza", "bakery", "ice_cream"),
    "scenic": lambda p: p.category in ("park", "landmark") or p.tags.get("tourism") == "viewpoint",
    "historic": lambda p: "historic" in p.tags,
}


@dataclass
class Weights:
    fit: float
    gap: float
    time_dev: float
    detour: float
    uncertainty: float

    @classmethod
    def from_settings(cls) -> "Weights":
        from app.core.config import get_settings

        s = get_settings()
        return cls(s.planner_w_fit, s.planner_w_gap, s.planner_w_time_dev, s.planner_w_detour,
                   s.planner_w_uncertainty)


@dataclass
class ScoredOption:
    meetup: MeetupOption
    destination: Place
    t_shared: float
    d_shared: float
    terms: dict[str, float]
    score: float

    @property
    def elapsed(self) -> float:
        return self.meetup.t_max + self.t_shared


def requires_open(intent: WalkIntent) -> bool:
    return any("open" in c for c in intent.hard_constraints)


def fit_term(meetup: Place, destination: Place, intent: WalkIntent) -> float:
    checks = []
    if intent.endpoint_type:
        checks.append(destination.category == intent.endpoint_type)
    for vibe in intent.vibes:
        test = VIBE_TESTS.get(vibe)
        if test:
            checks.append(test(meetup) or test(destination))
    return sum(checks) / len(checks) if checks else 0.5


def detour_term(a: Point, b: Point, option: MeetupOption) -> float:
    """How far walking to m is beyond walking straight towards each other; 0-1."""
    straight = haversine_m(*a, *b) * DETOUR_FACTOR
    if straight < 50:
        return 0.0
    return min(max((option.d_a + option.d_b) / straight - 1, 0.0), 1.0)


def score_options(
    a: Point, b: Point, cs: CandidateSet, intent: WalkIntent, weights: Weights, depart_at: datetime
) -> list[ScoredOption]:
    """Every feasible (meetup, destination) pair, best first. Failures go to cs.stats."""
    if cs.shared is None:
        return []
    need_open = requires_open(intent)
    options = []
    for i, m in enumerate(cs.meetups):
        for j, dest in enumerate(cs.destinations):
            t_shared = cs.shared.durations_min[i][j]
            if t_shared is None:
                _count(cs.stats, "shared_no_route")
                continue
            elapsed = m.t_max + t_shared
            if elapsed > intent.duration_min + ELAPSED_SLACK_MIN:
                _count(cs.stats, "elapsed_over_budget")
                continue
            open_at_arrival = is_open(dest.opening_hours, depart_at + timedelta(minutes=elapsed))
            if open_at_arrival is False:
                _count(cs.stats, "destination_known_closed")
                continue
            if need_open and open_at_arrival is not True:
                _count(cs.stats, "open_status_unconfirmed")
                continue
            terms = {
                "fit": fit_term(m.place, dest, intent),
                "gap": min(m.gap / MAX_GAP_MIN, 1.0),
                "time_dev": min(abs(elapsed - intent.duration_min) / (0.4 * intent.duration_min), 1.0),
                "detour": detour_term(a, b, m),
                "uncertainty": 0.0 if open_at_arrival is True else 1.0,
            }
            score = (
                weights.fit * terms["fit"]
                - weights.gap * terms["gap"]
                - weights.time_dev * terms["time_dev"]
                - weights.detour * terms["detour"]
                - weights.uncertainty * terms["uncertainty"]
            )
            options.append(
                ScoredOption(m, dest, t_shared, cs.shared.distances_m[i][j], terms, round(score, 6))
            )
    return rank(options)


def rank(options: list[ScoredOption]) -> list[ScoredOption]:
    """Deterministic: score, then gap, then place ids."""
    return sorted(
        options, key=lambda o: (-o.score, o.meetup.gap, o.meetup.place.id, o.destination.id)
    )


TOP_N = 3
MAX_DIRECTIONS_TRIES = 6  # ranked options checked with full directions to fill the top 3

CATEGORY_LABELS = {"ice_cream": "ice cream shop", "park_gate": "park gate", "subway_entrance": "subway entrance"}


def rationale(option: ScoredOption, gap: float, t_a: float, t_b: float, t_shared: float) -> str:
    m, d = option.meetup.place, option.destination
    hours = "opening hours unknown" if option.terms["uncertainty"] else "open when you arrive (per OSM)"
    return (
        f"Meet at {m.name}: A walks about {t_a:.0f} min, B about {t_b:.0f} min "
        f"(gap {gap:.1f} min). Then {t_shared:.0f} min together to {d.name} "
        f"({CATEGORY_LABELS.get(d.category, d.category)}, {hours})."
    )


def top_candidates(
    a: Point, b: Point, ranked: list[ScoredOption], intent: WalkIntent, ors, stats: dict
) -> list[MeetupCandidate]:
    """Fetch real directions for the best options and re-check them with those legs.

    Raises ProviderError when routing fails; a leg is never drawn without ORS geometry.
    """
    result: list[MeetupCandidate] = []
    for option in ranked[:MAX_DIRECTIONS_TRIES]:
        if len(result) == TOP_N:
            break
        m, d = option.meetup.place, option.destination
        a_leg: RouteLeg = ors.walk(a, (m.lat, m.lon))
        b_leg: RouteLeg = ors.walk(b, (m.lat, m.lon))
        shared_leg: RouteLeg = ors.walk((m.lat, m.lon), (d.lat, d.lon))
        gap = abs(a_leg.duration_min - b_leg.duration_min)
        elapsed = max(a_leg.duration_min, b_leg.duration_min) + shared_leg.duration_min
        if gap > MAX_GAP_MIN or elapsed > intent.duration_min + ELAPSED_SLACK_MIN:
            _count(stats, "directions_broke_constraint")
            continue
        result.append(
            MeetupCandidate(
                id=f"{m.id}>{d.id}",
                meeting_place_id=m.id,
                endpoint_place_id=d.id,
                a_leg=a_leg,
                b_leg=b_leg,
                shared_leg=shared_leg,
                arrival_gap_min=round(gap, 2),
                total_elapsed_min=round(elapsed, 2),
                score=option.score,
                rationale=rationale(option, gap, a_leg.duration_min, b_leg.duration_min,
                                    shared_leg.duration_min),
            )
        )
    return result


# --- Fallback ladder (section 6.4) ---

# Drop counter -> (constraint that failed, one suggested change)
FAILURE_REASONS = {
    "meetup_no_route": ("route_exists", "longer_time"),
    "shared_no_route": ("route_exists", "closer_destination"),
    "meetup_over_time_share": ("time_budget", "longer_time"),
    "elapsed_over_budget": ("time_budget", "closer_destination"),
    "meetup_gap_over_max": ("fair_gap", "longer_time"),
    "destination_known_closed": ("destination_open", "relaxed_preference"),
    "open_status_unconfirmed": ("destination_open", "relaxed_preference"),
    "directions_broke_constraint": ("time_budget", "longer_time"),
}
SUGGESTIONS = {
    "longer_time": "Allow a longer walk, for example {longer} minutes.",
    "closer_destination": "Pick a destination closer to the meetup point, or allow {longer} minutes.",
    "relaxed_preference": "Relax a preference: allow any destination type or drop 'open now'.",
}


class PlanFailure(BaseModel):
    constraint: str  # which hard constraint failed most often
    count: int
    suggestion_type: str  # longer_time / closer_destination / relaxed_preference
    suggestion: str


class PlanResult(BaseModel):
    status: str  # proposed / no_feasible_plan / routing_unavailable / places_unavailable
    candidates: list[MeetupCandidate] = []
    places: dict[str, Place] = {}  # meeting and endpoint places of the candidates
    failure: PlanFailure | None = None
    error: str | None = None
    stats: dict[str, int] = {}


def explain_failure(stats: dict[str, int], intent: WalkIntent) -> PlanFailure:
    longer = min(intent.duration_min + 10, 60)
    counts: dict[str, int] = {}
    first_key: dict[str, str] = {}
    for key, (constraint, _) in FAILURE_REASONS.items():
        if stats.get(key):
            counts[constraint] = counts.get(constraint, 0) + stats[key]
            if constraint not in first_key or stats[key] > stats[first_key[constraint]]:
                first_key[constraint] = key
    if not counts:
        # Nothing to filter: OSM had no candidate places of the wanted kind nearby.
        missing = "destination" if stats.get("meetup_kept") else "meetup"
        return PlanFailure(
            constraint=f"no_{missing}_places",
            count=0,
            suggestion_type="relaxed_preference",
            suggestion=SUGGESTIONS["relaxed_preference"],
        )
    constraint = max(sorted(counts), key=lambda c: counts[c])
    suggestion_type = FAILURE_REASONS[first_key[constraint]][1]
    return PlanFailure(
        constraint=constraint,
        count=counts[constraint],
        suggestion_type=suggestion_type,
        suggestion=SUGGESTIONS[suggestion_type].format(longer=longer),
    )


def plan_walk(
    a: Point, b: Point, intent: WalkIntent, overpass, ors, depart_at: datetime,
    weights: Weights | None = None,
) -> PlanResult:
    """Full deterministic planning. Never returns a route ORS did not produce."""
    weights = weights or Weights.from_settings()
    try:
        cs = generate_candidates(a, b, intent, overpass, ors, depart_at)
        ranked = score_options(a, b, cs, intent, weights, depart_at)
        top = top_candidates(a, b, ranked, intent, ors, cs.stats) if ranked else []
    except ProviderError as e:
        status = "places_unavailable" if e.code == "places_unavailable" else "routing_unavailable"
        log.warning("planner failed: %s (%s)", status, e.message)
        return PlanResult(status=status, error=e.message)

    cs.stats["feasible_options"] = len(ranked)
    if not top:
        failure = explain_failure(cs.stats, intent)
        log.info("planner: no feasible plan, %s failed %d times", failure.constraint, failure.count)
        return PlanResult(status="no_feasible_plan", failure=failure, stats=cs.stats)

    places = {o.meetup.place.id: o.meetup.place for o in ranked}
    places.update({o.destination.id: o.destination for o in ranked})
    used = {c.meeting_place_id for c in top} | {c.endpoint_place_id for c in top}
    return PlanResult(
        status="proposed",
        candidates=top,
        places={pid: places[pid] for pid in sorted(used)},
        stats=cs.stats,
    )
