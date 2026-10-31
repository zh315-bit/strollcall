"""Solo mode: one person, one start point, a walk to a place that fits their wish.

The same rules as the two-person planner, minus the meetup step: destinations of the wanted type,
known-closed places dropped, the crowd proxies when asked, the time budget (no tolerance when
strict), wishes read by Muse Spark in the fit, real walking legs only. Nothing is stored.
"More options" (services/options.py): pace and avoid through the routing view, a loop back to the
start, places of the kinds asked for passed (soft), stops on the route, an open destination.
"""

import logging
from datetime import datetime, timedelta

from pydantic import BaseModel

from app.core.errors import ProviderError
from app.core.geo import haversine_m
from app.core.hours import is_open
from app.models.schemas import Place, RouteLeg, WalkIntent, WalkOptions
from app.services.planner import (
    CATEGORY_LABELS, CROWD_NOTE, CROWD_NOTE_NO_DATA, DETOUR_FACTOR, VIBE_TESTS, WALK_M_PER_MIN,
    PlanFailure, Weights, avoids_crowds, destination_types, drop_crowded, explain_failure, pass_by_term,
    passed_on, requires_open, time_slack,
)

log = logging.getLogger(__name__)

Point = tuple[float, float]
MIN_SHARE = 0.6  # a walk shorter than this share of the wish is not what they asked for
SHORTLIST = 12  # destinations sent to one routing matrix call
TOP_N = 6  # six options close the ring of pages on the plan screen
MAX_DIRECTIONS_TRIES = 12
WISH_WINDOW_MIN = 4.0


class SoloCandidate(BaseModel):
    id: str  # the destination's place id
    destination_place_id: str
    leg: RouteLeg
    return_leg: RouteLeg | None = None  # a loop: from the destination back to the start
    stops: list[dict] = []  # places on the route the walker asked to stop at, in order
    passes: list[str] = []  # "Pass by" kinds this walk really passes (map data)
    total_min: float
    score: float
    rationale: str


class SoloPlan(BaseModel):
    status: str  # proposed / no_feasible_plan / routing_unavailable / places_unavailable
    candidates: list[SoloCandidate] = []
    places: dict[str, Place] = {}
    failure: PlanFailure | None = None
    error: str | None = None
    notes: list[str] = []
    stats: dict[str, int] = {}


def _count(stats: dict, key: str, n: int = 1) -> None:
    stats[key] = stats.get(key, 0) + n


def solo_fit(dest: Place, intent: WalkIntent, wishes=None) -> tuple[float, list[str]]:
    """0-1 fit and the parts of the wish this place meets (for the explanation)."""
    from app.services.wishes import REQUIREMENTS

    scores, met = [], []
    if intent.endpoint_type:
        ok = dest.category == intent.endpoint_type
        scores.append(float(ok))
        if ok:
            met.append(intent.endpoint_type.replace("_", " "))
    for vibe in intent.vibes:
        test = VIBE_TESTS.get(vibe)
        if test:
            scores.append(float(test(dest)))
            if test(dest):
                met.append(vibe)
    for w in (wishes.items if wishes else []):
        req = REQUIREMENTS[w.requirement]
        if req.target == "meetup":
            continue  # no meetup point when walking alone
        status = req.check(dest)
        scores.append(1.0 if status is True else 0.0 if status is False else 0.3)
        if status is True:
            met.append(req.description.split(" (")[0].replace("destination ", ""))
    return (sum(scores) / len(scores) if scores else 0.5), met


def _plan(origin: Point, intent: WalkIntent, places, routing, depart_at: datetime, wishes, weights,
          pass_by=None, options: WalkOptions | None = None) -> SoloPlan:
    from app.services.options import GRAPH_M_PER_MIN, describe, kinds_passed, mark_stops, pace_m_per_min

    options = options or WalkOptions()
    loop = options.shape == "loop"
    legs_per_walk = 2 if loop else 1
    speed = WALK_M_PER_MIN * pace_m_per_min(options) / GRAPH_M_PER_MIN  # straight-line estimates
    stats: dict[str, int] = {}
    slack = time_slack(intent)
    reach_m = (intent.duration_min + slack) / legs_per_walk * speed / DETOUR_FACTOR * 1.1
    radius = int(min(max(reach_m, 400), 2000))
    fetched = places.destination_candidates(*origin, radius, destination_types(intent))
    _count(stats, "destination_fetched", len(fetched))
    if avoids_crowds(intent) and hasattr(places, "crowd_risk"):
        fetched = drop_crowded(places, fetched, stats, "destination_excluded_crowd_proxy")
    arrive_at = depart_at + timedelta(minutes=intent.duration_min)

    ranked = []
    for p in fetched:
        if is_open(p.opening_hours, arrive_at) is False:
            _count(stats, "destination_known_closed")
            continue
        est = haversine_m(*origin, p.lat, p.lon) * DETOUR_FACTOR / speed * legs_per_walk
        if est > intent.duration_min + slack + 2:
            _count(stats, "destination_too_far_estimate")
            continue
        fit, _ = solo_fit(p, intent, wishes)
        target = 0.9 * intent.duration_min
        ranked.append((abs(est - target) > WISH_WINDOW_MIN, -fit, abs(est - target), p.id, p))
    ranked.sort(key=lambda o: o[:4])
    shortlist = [o[-1] for o in ranked[:SHORTLIST]]
    stats["destination_shortlisted"] = len(shortlist)
    if not shortlist:
        return SoloPlan(status="no_feasible_plan", stats=stats)

    times = routing.matrix([origin], [(p.lat, p.lon) for p in shortlist],
                           limit_min=(intent.duration_min + slack) / legs_per_walk)
    need_open = requires_open(intent)
    scored = []
    for p, t_out in zip(shortlist, times.durations_min[0]):
        if t_out is None:
            _count(stats, "no_route")
            continue
        t = t_out * legs_per_walk  # a loop: about as long back as out
        if t > intent.duration_min + slack:
            _count(stats, "elapsed_over_budget")
            continue
        if t < MIN_SHARE * intent.duration_min:
            _count(stats, "too_short")
            continue
        open_now = is_open(p.opening_hours, depart_at + timedelta(minutes=t_out))
        if open_now is False:
            _count(stats, "destination_known_closed")
            continue
        if need_open and open_now is not True:
            _count(stats, "open_status_unconfirmed")
            continue
        fit, met = solo_fit(p, intent, wishes)
        time_dev = min(abs(t - intent.duration_min) / (0.4 * intent.duration_min), 1.0)
        score = (weights.fit * fit - weights.time_dev * time_dev - weights.uncertainty * (0.0 if open_now else 1.0)
                 + weights.pass_by * pass_by_term([(origin, (p.lat, p.lon))], pass_by))
        scored.append((round(score, 6), p.id, p, met, open_now))
    scored.sort(key=lambda s: (-s[0], s[1]))
    stats["feasible_options"] = len(scored)

    candidates = []
    for score, pid, p, met, open_now in scored[:MAX_DIRECTIONS_TRIES]:
        # Without "Pass by" kinds the planner's order stands; with them, every walk tried is routed
        # and rescored by what it really passes.
        if len(candidates) == TOP_N and not options.pass_kinds:
            break
        dest = (p.lat, p.lon)
        leg = routing.walk(origin, dest)
        back = None
        if loop:
            back = (routing.walk_back(dest, origin, origin, dest) if hasattr(routing, "walk_back")
                    else routing.walk(dest, origin))
        total = leg.duration_min + (back.duration_min if back else 0.0)
        if total > intent.duration_min + slack:
            _count(stats, "directions_broke_constraint")
            continue
        legs = [leg] + ([back] if back else [])
        passes = kinds_passed(legs, options.pass_kinds, getattr(routing, "pois", None), places)
        if options.pass_kinds:
            score = round(score + weights.pass_by * len(passes) / len(options.pass_kinds), 6)
        stops = mark_stops(legs, options.stops, options.pass_kinds)
        leg, back = legs[0], (legs[1] if back else None)
        hours = "open when you arrive, per OSM" if open_now else "opening hours unknown"
        suits = f", for you: {', '.join(met)}" if met else ""
        walk = (f"Walk about {leg.duration_min:.0f} min to {p.name}" if not back else
                f"Walk about {leg.duration_min:.0f} min to {p.name} and {back.duration_min:.0f} min back to your start,")
        extra = describe(passes, stops, options.stops)
        candidates.append(SoloCandidate(
            id=pid, destination_place_id=pid, leg=leg, return_leg=back, stops=stops, passes=passes,
            total_min=round(total, 2), score=score,
            rationale=(f"{walk} ({CATEGORY_LABELS.get(p.category, p.category)}{suits}, {hours})."
                       + "".join(f" Passes {n}." for n in passed_on(legs, pass_by))
                       + (f" {extra}" if extra else "")),
        ))
    if options.pass_kinds:
        candidates.sort(key=lambda c: (-c.score, c.id))
    candidates = candidates[:TOP_N]
    if not candidates:
        return SoloPlan(status="no_feasible_plan", stats=stats)
    return SoloPlan(status="proposed", candidates=candidates,
                    places={c.destination_place_id: next(s[2] for s in scored if s[1] == c.id) for c in candidates},
                    stats=stats)


def _solo_failure(stats: dict, intent: WalkIntent, replan) -> PlanFailure:
    """Reuse the two-person explanation by mapping solo counters onto its stages."""
    mapped = {
        "meetup_kept": 1,  # there is no meetup stage alone
        "destination_fetched": stats.get("destination_fetched", 0),
        "destination_kept": stats.get("destination_shortlisted", 0),
        "destination_known_closed": stats.get("destination_known_closed", 0),
        "elapsed_over_budget": stats.get("elapsed_over_budget", 0) + stats.get("destination_too_far_estimate", 0)
                               + stats.get("directions_broke_constraint", 0) + stats.get("too_short", 0),
        "open_status_unconfirmed": stats.get("open_status_unconfirmed", 0),
        "shared_no_route": stats.get("no_route", 0),
    }
    return explain_failure(mapped, intent, replan)


def plan_solo(origin: Point, intent: WalkIntent, places, routing, depart_at: datetime, wishes=None,
              weights: Weights | None = None, pass_by=None, options: WalkOptions | None = None) -> SoloPlan:
    from app.services.options import honored, routing_view, with_options

    weights = weights or Weights.from_settings()
    intent = with_options(intent, options)
    plain = routing
    routing = routing_view(routing, options)
    try:
        plan = _plan(origin, intent, places, routing, depart_at, wishes, weights, pass_by, options)
    except ProviderError as e:
        status = "places_unavailable" if e.code == "places_unavailable" else "routing_unavailable"
        return SoloPlan(status=status, error=e.message)
    if avoids_crowds(intent):
        plan.notes.append(CROWD_NOTE if hasattr(places, "crowd_risk") else CROWD_NOTE_NO_DATA)
    if not honored(plain, options):
        plan.notes.append("Pace and Avoid apply only on our own walking map; this start uses another routing engine.")
    if plan.status == "no_feasible_plan":
        replan = None
        if getattr(routing, "name", "") == "local":  # cheap to replan only on the local graph
            def replan(i):
                try:
                    return _plan(origin, i, places, routing, depart_at, wishes, weights, pass_by,
                                 options).status == "proposed"
                except ProviderError:
                    return False
        plan.failure = _solo_failure(plan.stats, intent, replan)
    log.info("solo plan: %s", plan.status)
    return plan
