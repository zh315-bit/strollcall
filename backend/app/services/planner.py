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
from app.models.schemas import JointPreference, MeetupCandidate, Place, RouteLeg, TravelMatrix, WalkIntent
from app.providers.overpass import DESTINATION_TYPES

log = logging.getLogger(__name__)

Point = tuple[float, float]  # (lat, lon)

MAX_MEETUPS_QUERIED = 20  # one [A, B] x 20 matrix call
MAX_MEETUPS_KEPT = 10  # the doc's 5-10; fewer survive when fewer pass the filters
MAX_DESTINATIONS = 4  # one kept x 4 matrix call
MEETUP_TIME_SHARE = 0.6  # max(tA, tB) <= duration * 0.6
MAX_GAP_MIN = 5.0
ELAPSED_SLACK_MIN = 3.0
WALK_M_PER_MIN = 83.0  # ORS foot-walking is about 5 km/h
DETOUR_FACTOR = 1.3  # walking distance / straight-line distance, rough
DEDUPE_M = 40.0  # meetup points closer than this are the same spot
# Equal-time street intersections (local routing only): arrival gap at most this, spread out.
INTERSECTION_MAX_GAP_MIN = 2.0
INTERSECTION_SPACING_M = 100.0
MAX_INTERSECTIONS = 4
CONTOUR_GAP_MIN = 0.5  # debug output: nodes where A and B arrive within 30 s of each other
CONTOUR_MAX_POINTS = 400


def time_slack(intent: WalkIntent) -> float:
    """Minutes a plan may run over the budget: none when someone stated a hard limit."""
    return 0.0 if intent.duration_strict else ELAPSED_SLACK_MIN


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


SPLIT_RESERVE_QUERY = 4  # meetup points of a split category always sent to the matrix
SPLIT_RESERVE_KEPT = 3  # ... and kept after the gap filter, if feasible
# A destination type or vibe that a meetup point can satisfy, so the two people can be served
# by different parts of the walk ("meet at the park for B, end at the cafe for A").
MEETUP_MATCH = {"park": ("park", "park_gate"), "landmark": ("landmark",)}
VIBE_MEETUP = {"green": ("park", "park_gate"), "shady": ("park", "park_gate"), "scenic": ("park", "landmark")}


def split_categories(people: dict[str, WalkIntent] | None) -> list[str]:
    """Meetup categories that would serve one person while the destination serves the other."""
    if not people or len(people) != 2:
        return []
    a, b = people["A"], people["B"]
    cats: set[str] = set()
    for me, other in ((a, b), (b, a)):
        if not other.endpoint_type:
            continue
        if me.endpoint_type in MEETUP_MATCH and me.endpoint_type != other.endpoint_type:
            cats |= set(MEETUP_MATCH[me.endpoint_type])
        for vibe in me.vibes:
            if vibe in VIBE_MEETUP and other.endpoint_type not in MEETUP_MATCH:
                cats |= set(VIBE_MEETUP[vibe])
    return sorted(cats)


def select_meetup_points(places: list[Place], mid: Point, limit: int, stats: dict,
                         reserve: list[str] | None = None) -> list[Place]:
    """Nearest to the midpoint first, one per spot, at most `limit`.

    With `reserve`, the nearest few of those categories go first, so a split plan is possible.
    """
    by_distance = sorted(places, key=lambda p: (haversine_m(*mid, p.lat, p.lon), p.id))
    reserved = [p for p in by_distance if reserve and p.category in reserve][:SPLIT_RESERVE_QUERY]
    ordered = reserved + [p for p in by_distance if p not in reserved]
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
    points: list[Place], times: TravelMatrix, duration_min: int, stats: dict,
    reserve: list[str] | None = None,
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
    if reserve:
        extra = [o for o in feasible[MAX_MEETUPS_KEPT:] if o.place.category in reserve][:SPLIT_RESERVE_KEPT]
        kept += extra
        if extra:
            stats["meetup_kept_for_split"] = len(extra)
    if len(feasible) > len(kept):
        stats["meetup_beyond_keep_limit"] = len(feasible) - len(kept)
    return kept


def equal_time_intersections(routing, a: Point, b: Point, duration_min: int, stats: dict) -> list[MeetupOption]:
    """Named street intersections A and B reach at about the same time, one per 100 m.

    Only with the local graph (routing.equal_time_nodes); other engines return [].
    """
    if not hasattr(routing, "equal_time_nodes"):
        return []
    from app.providers.local_routing import OutsideCoverage

    try:
        nodes, ta, tb = routing.equal_time_nodes(a, b, duration_min * MEETUP_TIME_SHARE, INTERSECTION_MAX_GAP_MIN)
    except OutsideCoverage:
        return []
    g = routing.graph
    order = sorted(range(len(nodes)), key=lambda k: (abs(ta[k] - tb[k]), max(ta[k], tb[k]), int(g.osmid[nodes[k]])))
    chosen: list[MeetupOption] = []
    for k in order:
        n = int(nodes[k])
        name = g.intersection_name(n) if g.degree[n] >= 3 else None
        if not name:
            continue
        lat, lon = float(g.lat[n]), float(g.lon[n])
        if any(haversine_m(lat, lon, c.place.lat, c.place.lon) < INTERSECTION_SPACING_M for c in chosen):
            continue
        place = Place(id=f"node/{int(g.osmid[n])}", name=name, lat=lat, lon=lon, category="intersection")
        t_a, t_b = round(float(ta[k]), 2), round(float(tb[k]), 2)
        chosen.append(MeetupOption(place, t_a, t_b, t_a * g.m_per_min, t_b * g.m_per_min))
        if len(chosen) == MAX_INTERSECTIONS:
            break
    stats["intersection_equal_time_nodes"] = len(nodes)
    stats["intersection_kept"] = len(chosen)
    return chosen


def equal_time_contour(routing, a: Point, b: Point, duration_min: int) -> list[list[float]]:
    """Debug: [lat, lon] of graph nodes where A and B arrive within 30 s of each other."""
    if not hasattr(routing, "equal_time_nodes"):
        return []
    from app.providers.local_routing import OutsideCoverage

    try:
        nodes, _, _ = routing.equal_time_nodes(a, b, duration_min * MEETUP_TIME_SHARE, CONTOUR_GAP_MIN)
    except OutsideCoverage:
        return []
    step = max(1, len(nodes) // CONTOUR_MAX_POINTS)
    g = routing.graph
    return [[round(float(g.lat[n]), 6), round(float(g.lon[n]), 6)] for n in nodes[::step]]


CROWD_WORDS = ("crowd", "busy", "tourist", "packed", "people")
CROWD_NOTE = "We can't check crowd levels; we avoided major transit hubs and large plazas."
CROWD_NOTE_NO_DATA = "We can't check crowd levels here, so we couldn't avoid busy places."


def avoids_crowds(intent: WalkIntent) -> bool:
    return any(w in a.lower() for a in intent.avoid for w in CROWD_WORDS)


def drop_crowded(places_provider, items: list, stats: dict, key: str, place=lambda x: x) -> list:
    """Remove likely-crowded places (transit hubs, large plazas) using the provider's OSM proxies."""
    kept = []
    for item in items:
        if places_provider.crowd_risk(place(item)):
            _count(stats, key)
        else:
            kept.append(item)
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
    types: list[str] | None = None,
    wishes=None,
) -> list[Place]:
    """Destinations whose estimated shared walk is closest to the time left.

    With wishes, places that meet more of them come first among those within
    WISH_WINDOW_MIN of the ideal shared-walk time.
    """
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
    met = {p.id: _wishes_met(wishes, p) for _, _, p in scored} if wishes else {}
    scored.sort(key=lambda s: (s[0] > WISH_WINDOW_MIN, -met.get(s[1], 0), s[0], s[1]))
    if len(scored) > limit:
        stats["destination_beyond_limit"] = len(scored) - limit
    if len(types or []) > 1:
        # Two people asked for different types: take turns so each type is represented.
        buckets = [[p for _, _, p in scored if p.category == t] for t in types]
        mixed = [p for group in zip(*[b + [None] * limit for b in buckets]) for p in group if p]
        return mixed[:limit]
    return [p for _, _, p in scored[:limit]]


WISH_WINDOW_MIN = 4.0
SPLIT_MEETUPS_FOR_DESTINATIONS = 2
SPLIT_DESTINATIONS_EACH = 2


def split_destinations(places, kept, chosen, reserve, types, intent, arrive_at, stats) -> list[Place]:
    """Destinations of the other person's type that fit the time left after a split meetup.

    The main shortlist is sized for the typical meetup; a park gate further out needs a
    closer cafe, or every split combination runs over the budget.
    """
    other_types = [t for t in types if t not in MEETUP_MATCH]
    split = sorted((m for m in kept if m.place.category in reserve), key=lambda m: (m.gap, m.place.id))
    have = {p.id for p in chosen}
    slack = time_slack(intent)
    added: list[Place] = []
    for m in split[:SPLIT_MEETUPS_FOR_DESTINATIONS]:
        left = intent.duration_min + slack - m.t_max
        options = []
        for p in places:
            if p.category not in other_types or p.id in have or is_open(p.opening_hours, arrive_at) is False:
                continue
            est = haversine_m(m.place.lat, m.place.lon, p.lat, p.lon) * DETOUR_FACTOR / WALK_M_PER_MIN
            if est <= left - 1:  # a minute of margin for the rough estimate
                options.append((abs(est - 0.8 * left), p.id, p))
        for _, pid, p in sorted(options)[:SPLIT_DESTINATIONS_EACH]:
            have.add(pid)
            added.append(p)
    if added:
        stats["destination_added_for_split"] = len(added)
    return added




def _wishes_met(wishes, destination: Place) -> int:
    from app.services.wishes import REQUIREMENTS

    return sum(
        REQUIREMENTS[w.requirement].target in ("destination", "either")
        and REQUIREMENTS[w.requirement].check(destination) is True
        for w in wishes.items
    )


def generate_candidates(
    a: Point, b: Point, intent: WalkIntent, overpass, ors, depart_at: datetime,
    endpoint_options: list[str] | None = None,
    wishes=None,
    people: dict[str, WalkIntent] | None = None,
) -> CandidateSet:
    """Step 1 of section 6.2. Raises ProviderError if Overpass or ORS fail."""
    stats: dict[str, int] = {}
    mid = midpoint(a, b)
    radius = meetup_search_radius(a, b)
    fetched = overpass.meetup_candidates(*mid, radius)
    stats["meetup_fetched"] = len(fetched)
    crowd_filter = avoids_crowds(intent) and hasattr(overpass, "crowd_risk")
    if crowd_filter:
        fetched = drop_crowded(overpass, fetched, stats, "meetup_excluded_crowd_proxy")
    reserve = split_categories(people)
    points = select_meetup_points(fetched, mid, MAX_MEETUPS_QUERIED, stats, reserve)
    stats["meetup_queried"] = len(points)
    kept = []
    if points:
        times = ors.matrix([a, b], [(p.lat, p.lon) for p in points],
                           limit_min=intent.duration_min * MEETUP_TIME_SHARE)
        kept = filter_meetups(points, times, intent.duration_min, stats, reserve)
    corners = equal_time_intersections(ors, a, b, intent.duration_min, stats)
    if crowd_filter:
        corners = drop_crowded(overpass, corners, stats, "meetup_excluded_crowd_proxy", lambda m: m.place)
    kept += corners
    stats["meetup_kept"] = len(kept)
    if not kept:
        return _done(CandidateSet([], [], None, stats))

    target = remaining_minutes(intent, kept)
    center, dest_radius = destination_search(kept, target)
    types = destination_types(intent)
    if intent.endpoint_type is None and endpoint_options:
        types = sorted(set(endpoint_options))  # A and B asked for different types
    fetched_dest = overpass.destination_candidates(*center, dest_radius, types)
    if crowd_filter:
        fetched_dest = drop_crowded(overpass, fetched_dest, stats, "destination_excluded_crowd_proxy")
    stats["destination_fetched"] = len(fetched_dest)
    arrive_at = depart_at + timedelta(minutes=intent.duration_min)
    destinations = select_destinations(fetched_dest, kept, target, arrive_at, MAX_DESTINATIONS, stats,
                                       types if len(types) > 1 and endpoint_options else None, wishes)
    if reserve:
        destinations += split_destinations(fetched_dest, kept, destinations, reserve, types, intent,
                                           arrive_at, stats)
    stats["destination_kept"] = len(destinations)
    if not destinations:
        return _done(CandidateSet(kept, [], None, stats))

    shared = ors.matrix([(m.place.lat, m.place.lon) for m in kept], [(d.lat, d.lon) for d in destinations],
                        limit_min=intent.duration_min + time_slack(intent))
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
    named_place: float = 0.1  # bonus for a named POI over a street intersection
    pass_by: float = 0.25  # bonus per share of asked-for places the walk is likely to pass

    @classmethod
    def from_settings(cls) -> "Weights":
        from app.core.config import get_settings

        s = get_settings()
        return cls(s.planner_w_fit, s.planner_w_gap, s.planner_w_time_dev, s.planner_w_detour,
                   s.planner_w_uncertainty, s.planner_w_named_place, s.planner_w_pass_by)


# --- "Pass by" a place (soft preference from the Near you card) ---

PASS_BY_NEAR_M = 150.0  # scoring: a straight line between the walk's points comes this close
PASS_BY_ROUTE_M = 60.0  # explanation: the real route comes this close, else it is not mentioned


def _segment_m(p: Point, a: Point, b: Point) -> float:
    """Meters from p to the segment a-b (local flat approximation)."""
    import math

    k = math.cos(math.radians(p[0])) * 111_320.0
    ax, ay, bx, by, px, py = a[1] * k, a[0] * 111_320.0, b[1] * k, b[0] * 111_320.0, p[1] * k, p[0] * 111_320.0
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def pass_by_term(segments: list[tuple[Point, Point]], pass_by) -> float:
    """Share (0-1) of the asked-for places some segment passes within PASS_BY_NEAR_M of."""
    if not pass_by:
        return 0.0
    hit = sum(any(_segment_m(tuple(q), a, b) <= PASS_BY_NEAR_M for q in pb.pts for a, b in segments) for pb in pass_by)
    return hit / len(pass_by)


def passed_on(legs: list[RouteLeg], pass_by) -> list[str]:
    """Names of the asked-for places the real legs pass within PASS_BY_ROUTE_M of."""
    names = []
    for pb in pass_by or []:
        if any(_segment_m(tuple(q), g[i], g[i + 1]) <= PASS_BY_ROUTE_M
               for leg in legs for g in [leg.geometry] for i in range(len(g) - 1) for q in pb.pts):
            names.append(pb.name)
    return names


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


DESTINATION_WORDS = {
    "cafe": ("cafe", "café", "coffee"), "bookstore": ("bookstore", "bookshop", "books"),
    "park": ("park",), "bakery": ("bakery", "pastr", "bread"), "ice_cream": ("ice cream", "ice_cream", "gelato"),
    "landmark": ("landmark", "monument", "memorial", "museum"),
}
JOINT_WEIGHTS = {"shared": 0.5, "a": 0.25, "b": 0.25}


def preference_test(phrase: str):
    """A deterministic check for one preference phrase, or None if we cannot measure it."""
    p = phrase.lower()
    if p.startswith("avoid") or "avoid " in p:
        return None  # e.g. "avoid traffic": no data to check it
    for dtype, words in DESTINATION_WORDS.items():
        if any(w in p for w in words):
            return lambda m, d, t=dtype: d.category == t or (t == "park" and m.category in ("park", "park_gate"))
    for vibe, test in VIBE_TESTS.items():
        if vibe in p:
            return lambda m, d, f=test: f(m) or f(d)
    return None


def joint_fit(meetup: Place, destination: Place, joint: JointPreference | None, wishes=None) -> float | None:
    """Both people's preferences: shared 0.5, A's own 0.25, B's own 0.25 (renormalised).

    A person's own group includes their wishes (services/wishes.py): 1 met, 0 not met,
    UNKNOWN_SCORE when the tag is missing.
    """
    from app.services.wishes import requirement_score

    groups = {"shared": [], "a": [], "b": []}
    if joint is not None:
        for group, phrases in (("shared", joint.shared_vibes), ("a", joint.a_priorities), ("b", joint.b_priorities)):
            groups[group] += [float(t(meetup, destination)) for t in map(preference_test, phrases) if t]
    if wishes is not None:
        for w in wishes.items:
            groups[w.who.lower()].append(requirement_score(w, meetup, destination))
    total, weight = 0.0, 0.0
    for group, scores in groups.items():
        if scores:
            total += JOINT_WEIGHTS[group] * sum(scores) / len(scores)
            weight += JOINT_WEIGHTS[group]
    return total / weight if weight else None


def fit_term(meetup: Place, destination: Place, intent: WalkIntent, joint: JointPreference | None = None,
             wishes=None) -> float:
    if joint is not None or wishes is not None:
        value = joint_fit(meetup, destination, joint, wishes)
        if value is not None:
            return value
    checks = []
    if intent.endpoint_type:
        checks.append(destination.category == intent.endpoint_type)
    for vibe in intent.vibes:
        test = VIBE_TESTS.get(vibe)
        if test:
            checks.append(test(meetup) or test(destination))
    return sum(checks) / len(checks) if checks else 0.5


def served(meetup: Place, destination: Place, people: dict[str, WalkIntent] | None) -> dict[str, list[str]]:
    """Which part of the walk meets whose stated preference: {"meetup": ["B: park"], ...}."""
    out: dict[str, list[str]] = {"meetup": [], "destination": []}
    for who, intent in (people or {}).items():
        t = intent.endpoint_type
        if t:
            if destination.category == t:
                out["destination"].append(f"{who}: {t.replace('_', ' ')}")
            elif t in MEETUP_MATCH and meetup.category in MEETUP_MATCH[t]:
                out["meetup"].append(f"{who}: {t.replace('_', ' ')}")
        for vibe in intent.vibes:
            test = VIBE_TESTS.get(vibe)
            if test and test(meetup):
                out["meetup"].append(f"{who}: {vibe}")
            elif test and test(destination):
                out["destination"].append(f"{who}: {vibe}")
    return out


def _for_text(items: list[str]) -> str:
    """["B: park", "B: green"] -> "for B (park, green)"; both people listed in order."""
    by_person: dict[str, list[str]] = {}
    for item in items:
        who, what = item.split(": ", 1)
        by_person.setdefault(who, []).append(what)
    return "; ".join(f"for {who} ({', '.join(whats)})" for who, whats in sorted(by_person.items()))


def detour_term(a: Point, b: Point, option: MeetupOption) -> float:
    """How far walking to m is beyond walking straight towards each other; 0-1."""
    straight = haversine_m(*a, *b) * DETOUR_FACTOR
    if straight < 50:
        return 0.0
    return min(max((option.d_a + option.d_b) / straight - 1, 0.0), 1.0)


def score_options(
    a: Point, b: Point, cs: CandidateSet, intent: WalkIntent, weights: Weights, depart_at: datetime,
    joint: JointPreference | None = None, wishes=None, pass_by=None,
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
            if elapsed > intent.duration_min + time_slack(intent):
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
                "fit": fit_term(m.place, dest, intent, joint, wishes),
                "gap": min(m.gap / MAX_GAP_MIN, 1.0),
                "time_dev": min(abs(elapsed - intent.duration_min) / (0.4 * intent.duration_min), 1.0),
                "detour": detour_term(a, b, m),
                "uncertainty": 0.0 if open_at_arrival is True else 1.0,
                "named_place": 0.0 if m.place.category == "intersection" else 1.0,
                "pass_by": pass_by_term([(a, (m.place.lat, m.place.lon)), (b, (m.place.lat, m.place.lon)),
                                         ((m.place.lat, m.place.lon), (dest.lat, dest.lon))], pass_by),
            }
            score = (
                weights.fit * terms["fit"]
                - weights.gap * terms["gap"]
                - weights.time_dev * terms["time_dev"]
                - weights.detour * terms["detour"]
                - weights.uncertainty * terms["uncertainty"]
                + weights.named_place * terms["named_place"]
                + weights.pass_by * terms["pass_by"]
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


TOP_N = 6  # six options close the ring of pages on the plan screen
MAX_DIRECTIONS_TRIES = 12  # ranked options checked with full directions to fill the top 6

CATEGORY_LABELS = {"ice_cream": "ice cream shop", "park_gate": "park gate", "subway_entrance": "subway entrance",
                   "intersection": "street corner"}


def rationale(option: ScoredOption, gap: float, t_a: float, t_b: float, t_shared: float,
              people: dict[str, WalkIntent] | None = None) -> str:
    m, d = option.meetup.place, option.destination
    hours = "opening hours unknown" if option.terms["uncertainty"] else "open when you arrive, per OSM"
    who = served(m, d, people)
    meet_for = f", {_for_text(who['meetup'])}" if who["meetup"] else ""
    dest_for = f"{_for_text(who['destination'])}, " if who["destination"] else ""
    return (
        f"Meet at {m.name} ({CATEGORY_LABELS.get(m.category, m.category)}{meet_for}): A walks about "
        f"{t_a:.0f} min, B about {t_b:.0f} min (gap {gap:.1f} min). Then {t_shared:.0f} min together to "
        f"{d.name} ({CATEGORY_LABELS.get(d.category, d.category)}, {dest_for}{hours})."
    )


def top_candidates(
    a: Point, b: Point, ranked: list[ScoredOption], intent: WalkIntent, ors, stats: dict,
    people: dict[str, WalkIntent] | None = None, pass_by=None,
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
        gap = round(abs(a_leg.duration_min - b_leg.duration_min), 2)  # same value the page shows
        elapsed = max(a_leg.duration_min, b_leg.duration_min) + shared_leg.duration_min
        if gap > MAX_GAP_MIN or elapsed > intent.duration_min + time_slack(intent):
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
                                    shared_leg.duration_min, people)
                + "".join(f" Passes {n}." for n in passed_on([a_leg, shared_leg], pass_by)),
            )
        )
    return result


# --- Fallback ladder (section 6.4) ---

MAX_DURATION_MIN = 60  # WalkIntent's upper bound
DURATION_STEP_MIN = 5


class PlanFailure(BaseModel):
    # The constraint that emptied the pipeline: no_meetup_points / time_budget / fair_gap /
    # route_exists / no_destination_of_type / no_destinations / destination_open
    constraint: str
    count: int  # how many candidates it removed
    suggestion_type: str  # longer_time / relaxed_preference / closer_start
    suggestion: str
    needs_duration_min: int | None = None  # verified by replanning; None if not searched or not found
    verified: bool = False  # the suggestion was checked by replanning


class PlanResult(BaseModel):
    status: str  # proposed / no_feasible_plan / routing_unavailable / places_unavailable
    candidates: list[MeetupCandidate] = []
    places: dict[str, Place] = {}  # meeting and endpoint places of the candidates
    failure: PlanFailure | None = None
    error: str | None = None
    stats: dict[str, int] = {}
    debug: dict | None = None  # e.g. {"equal_time_contour": [[lat, lon], ...]} when asked
    notes: list[str] = []  # honest limits to show the users, e.g. that crowds cannot be checked


def binding_constraint(stats: dict[str, int], intent: WalkIntent) -> tuple[str, int]:
    """Where the pipeline ran out of candidates, and how many that step removed."""
    g = stats.get
    if not g("meetup_kept"):
        if not g("meetup_fetched") and not g("intersection_kept"):
            return "no_meetup_points", 0
        counts = {"time_budget": g("meetup_over_time_share", 0), "fair_gap": g("meetup_gap_over_max", 0),
                  "route_exists": g("meetup_no_route", 0)}
    elif not g("destination_kept"):
        if not g("destination_fetched"):
            return ("no_destination_of_type" if intent.endpoint_type else "no_destinations"), 0
        return "destination_open", g("destination_known_closed", 0)
    else:
        counts = {"time_budget": g("elapsed_over_budget", 0) + g("directions_broke_constraint", 0),
                  "destination_open": g("destination_known_closed", 0) + g("open_status_unconfirmed", 0),
                  "route_exists": g("shared_no_route", 0)}
    constraint = max(sorted(counts), key=lambda c: counts[c])
    return constraint, counts[constraint]


def relaxed(intent: WalkIntent) -> WalkIntent:
    """Any destination type, no 'open now'; duration, avoid and other limits unchanged."""
    return intent.model_copy(update={
        "endpoint_type": None,
        "hard_constraints": [c for c in intent.hard_constraints if "open" not in c],
    })


def explain_failure(stats, intent, replan=None) -> PlanFailure:
    """Pick the suggestion from the binding constraint; verify it by replanning when allowed.

    replan(intent) -> bool runs the planner again (cheap with the local graph); None skips it.
    """
    constraint, count = binding_constraint(stats, intent)
    wanted = (intent.endpoint_type or "destination").replace("_", " ")
    dest_problem = constraint in ("no_destination_of_type", "destination_open")

    def failure(kind, text, needs=None, verified=False):
        return PlanFailure(constraint=constraint, count=count, suggestion_type=kind, suggestion=text,
                           needs_duration_min=needs, verified=verified)

    if replan is None:
        if dest_problem:
            return failure("relaxed_preference", f"No {wanted} fits this walk; try allowing any destination.")
        return failure("longer_time", "Try allowing a longer walk.")

    if dest_problem and (intent.endpoint_type or requires_open(intent)) and replan(relaxed(intent)):
        return failure("relaxed_preference",
                       f"No {wanted} fits; any destination type works within {intent.duration_min} minutes.",
                       verified=True)
    for minutes in range(intent.duration_min + DURATION_STEP_MIN, MAX_DURATION_MIN + 1, DURATION_STEP_MIN):
        if replan(intent.model_copy(update={"duration_min": minutes})):
            return failure("longer_time", f"Needs about {minutes} minutes: try a {minutes}-minute walk.",
                           needs=minutes, verified=True)
    if not dest_problem and (intent.endpoint_type or requires_open(intent)):
        for minutes in range(intent.duration_min, MAX_DURATION_MIN + 1, DURATION_STEP_MIN):
            if replan(relaxed(intent).model_copy(update={"duration_min": minutes})):
                return failure("relaxed_preference",
                               f"Needs about {minutes} minutes and any destination type.",
                               needs=minutes, verified=True)
    return failure("closer_start",
                   f"Too far apart for a walk within {MAX_DURATION_MIN} minutes: pick start points closer together.",
                   verified=True)


def plan_walk(
    a: Point, b: Point, intent: WalkIntent, overpass, ors, depart_at: datetime,
    weights: Weights | None = None, debug: bool = False,
    joint: JointPreference | None = None, endpoint_options: list[str] | None = None, wishes=None,
    people: dict[str, WalkIntent] | None = None, pass_by=None,
) -> PlanResult:
    """Full deterministic planning. Never returns a route the routing engine did not produce.
    pass_by: places A asked to pass by (services/nearby.PassBy), a soft preference only."""
    weights = weights or Weights.from_settings()
    result = _plan(a, b, intent, overpass, ors, depart_at, weights, joint, endpoint_options, wishes, people,
                   pass_by)
    if avoids_crowds(intent):
        result.notes.append(CROWD_NOTE if hasattr(overpass, "crowd_risk") else CROWD_NOTE_NO_DATA)
    if result.status == "no_feasible_plan":
        # Replanning is cheap only on the local graph; ORS would spend quota, mocks lack data.
        replan = None
        if getattr(ors, "name", "") == "local":
            def replan(i):
                return _plan(a, b, i, overpass, ors, depart_at, weights, joint, endpoint_options,
                             wishes, people, pass_by).status == "proposed"
        result.failure = explain_failure(result.stats, intent, replan)
        log.info("planner: no feasible plan, binding %s; suggestion %s",
                 result.failure.constraint, result.failure.suggestion_type)
    if debug:
        result.debug = {"equal_time_contour": equal_time_contour(ors, a, b, intent.duration_min)}
    return result


def _plan(a, b, intent, overpass, ors, depart_at, weights, joint=None, endpoint_options=None,
          wishes=None, people=None, pass_by=None) -> PlanResult:
    try:
        cs = generate_candidates(a, b, intent, overpass, ors, depart_at, endpoint_options, wishes, people)
        ranked = score_options(a, b, cs, intent, weights, depart_at, joint, wishes, pass_by)
        top = top_candidates(a, b, ranked, intent, ors, cs.stats, people, pass_by) if ranked else []
    except ProviderError as e:
        status = "places_unavailable" if e.code == "places_unavailable" else "routing_unavailable"
        log.warning("planner failed: %s (%s)", status, e.message)
        return PlanResult(status=status, error=e.message)

    cs.stats["feasible_options"] = len(ranked)
    if not top:
        return PlanResult(status="no_feasible_plan", stats=cs.stats)  # failure filled by plan_walk

    places = {o.meetup.place.id: o.meetup.place for o in ranked}
    places.update({o.destination.id: o.destination for o in ranked})
    used = {c.meeting_place_id for c in top} | {c.endpoint_place_id for c in top}
    return PlanResult(
        status="proposed",
        candidates=top,
        places={pid: places[pid] for pid in sorted(used)},
        stats=cs.stats,
    )


def plan_for_two(
    a: Point, b: Point, a_intent: WalkIntent, b_intent: WalkIntent, joint: JointPreference,
    places, routing, depart_at: datetime, debug: bool = False, wishes=None, pass_by=None,
) -> PlanResult:
    """Plan for A and B: hard limits from both (combined_intent), fit from the joint preference
    and from the wishes Muse Spark mapped to checkable requirements."""
    from app.services.intent import combined_intent

    intent = combined_intent(a_intent, b_intent)
    options = [t for t in (a_intent.endpoint_type, b_intent.endpoint_type) if t]
    return plan_walk(a, b, intent, places, routing, depart_at, debug=debug, joint=joint,
                     endpoint_options=options if len(set(options)) > 1 else None, wishes=wishes,
                     people={"A": a_intent, "B": b_intent}, pass_by=pass_by)
