""""More options" on the New walk page, honored with map data only.

- Pace: 65 / 80 / 95 m/min. The walking graph is timed at 80 m/min (the "normal" pace); another
  pace scales every time the planner checks and the page shows.
- Avoid: stairs, busy avenues, major transit hubs, as penalties on graph edges flagged from
  OpenStreetMap (scripts/add_edge_flags.py). Penalties, not exclusions, and only as good as the
  map: the page says "based on map data" and promises no accessibility.
- Pass by: parks, waterfront, landmarks, public art, bookstores, markets. A soft preference: a
  walk that passes more of the kinds asked for scores higher; nothing is dropped for missing one.
  "Something else" typed there can add bridges, viewpoints, fountains, squares, cafes, bakeries or
  ice cream, or name places to pass (services/custom_options.py).
- Avoid: typed there can name places to keep away from: edges near them get a penalty too.
- Stops: up to 3 places on the route itself (no detour), preferring the kinds asked for. Typed
  there ("a coffee", "a bookstore") they must be of that kind, shops right on the route included.
- Destination must be open: OSM opening hours must say open at arrival (the existing hard
  constraint). Route shape (loop or one way) is in services/solo.py.

Nothing here reads crowds, safety, lighting, hills or weather: there is no reliable data for them.
"""

from app.models.schemas import RouteLeg, WalkIntent, WalkOptions

PACE_M_PER_MIN = {"relaxed": 65.0, "normal": 80.0, "brisk": 95.0}
GRAPH_M_PER_MIN = 80.0  # the walking graph's own pace (scripts/build_graph.py)
# Route POI categories (providers/route_pois.py) for each "Pass by" kind; waterfront is the
# shoreline and bookstores are shops in the place snapshot.
POI_KINDS = {
    "parks": ("park", "garden"),
    "landmarks": ("landmark", "historic site", "memorial", "notable building"),
    "public_art": ("artwork",),
    "markets": ("market",),
    "bridges": ("bridge",),
    "viewpoints": ("viewpoint",),
    "fountains": ("fountain",),
    "squares": ("square",),
}
# Shops in the place snapshot, passed when one is within SHOP_NEAR_M of the line.
SHOP_KINDS = {"bookstores": "bookstore", "cafes": "cafe", "bakeries": "bakery", "ice_cream": "ice_cream"}
KIND_LABELS = {"parks": "a park", "waterfront": "the waterfront", "landmarks": "a landmark",
               "public_art": "public art", "bookstores": "a bookstore", "markets": "a market",
               "bridges": "a bridge", "viewpoints": "a viewpoint", "fountains": "a fountain",
               "squares": "a square", "cafes": "a cafe", "bakeries": "a bakery", "ice_cream": "an ice cream shop"}
WATERFRONT_MIN_M = 100.0  # this much of the walk within 75 m of the shoreline counts as passing it
PLURALS = {"public_art": "artworks", "ice_cream": "ice cream shops", "waterfront": "waterfront"}
SHOP_NEAR_M = 40.0
AVOID_NEAR_M = 100.0  # graph edges this close to a place to avoid get AVOID_PLACE_PENALTY
STOP_EDGE_SHARE = 0.1  # no stop in the first or last tenth of the walk: that is the start or the end
OPEN_CONSTRAINT = "destination open on arrival"


def pace_m_per_min(options: WalkOptions | None) -> float:
    return PACE_M_PER_MIN[options.pace] if options else GRAPH_M_PER_MIN


def with_options(intent: WalkIntent, options: WalkOptions | None) -> WalkIntent:
    """The intent with "Destination must be open" as a hard constraint (planner.requires_open)."""
    if options and options.must_be_open and not any("open" in c for c in intent.hard_constraints):
        return intent.model_copy(update={"hard_constraints": [*intent.hard_constraints, OPEN_CONSTRAINT]})
    return intent


def avoid_places(options: WalkOptions | None) -> list:
    """The places typed under Avoid, from our data (services/nearby.PassBy: name and outline)."""
    if not options or not options.avoid_place_ids:
        return []
    from app.services.nearby import resolve_pass_by

    return resolve_pass_by(options.avoid_place_ids)


def routing_view(routing, options: WalkOptions | None):
    """The routing engine at the chosen pace and avoiding what was asked (local graph only; another
    engine is returned unchanged and the caller notes it)."""
    if not options or not hasattr(routing, "view"):
        return routing
    near = tuple((round(la, 5), round(lo, 5)) for p in avoid_places(options) for la, lo in p.pts)
    return routing.view(PACE_M_PER_MIN[options.pace], tuple(options.avoid), near)


def honored(routing, options: WalkOptions | None) -> bool:
    """False when pace or avoid were asked for but the engine cannot apply them."""
    if not options or (options.pace == "normal" and not options.avoid and not options.avoid_place_ids):
        return True
    return hasattr(routing, "view")


class SidedRouting:
    """Two-person planning with A's options: every walk or time from A's start uses A's view (pace,
    avoid); B and the shared walk use the plain engine. Same interface as LocalRouting."""

    name = "local"

    def __init__(self, base, a_point, a_view):
        self.base, self.a, self.a_view = base, tuple(a_point), a_view
        self.graph, self.pois = base.graph, base.pois

    def _for(self, p):
        return self.a_view if tuple(p) == self.a else self.base

    def matrix(self, sources, destinations, limit_min=None):
        from app.models.schemas import TravelMatrix

        rows = [self._for(s).matrix([s], destinations, limit_min=limit_min) for s in sources]
        return TravelMatrix(durations_min=[r.durations_min[0] for r in rows],
                            distances_m=[r.distances_m[0] for r in rows])

    def walk(self, start, end):
        return self._for(start).walk(start, end)

    def equal_time_nodes(self, a, b, max_minutes, max_gap):
        import numpy as np

        (na, sa), (nb, sb) = self.graph.snap(a), self.graph.snap(b)
        av, bv = self._for(a), self._for(b)
        ta = av._search(na, max_minutes)[0] + sa / av.m_per_min
        tb = bv._search(nb, max_minutes)[0] + sb / bv.m_per_min
        with np.errstate(invalid="ignore"):
            mask = np.isfinite(ta) & np.isfinite(tb) & (np.abs(ta - tb) <= max_gap) & (np.maximum(ta, tb) <= max_minutes)
        nodes = np.nonzero(mask)[0]
        return nodes, ta[nodes], tb[nodes]


def sided(routing, a_point, options: WalkOptions | None):
    view = routing_view(routing, options)
    return routing if view is routing else SidedRouting(routing, a_point, view)


def shops_along(geometry, categories: set[str], places) -> list[dict]:
    """Shops of these categories within SHOP_NEAR_M of the line, in walking order, each once:
    {id, name, category, lat, lon, along_m} like a route POI."""
    snap = getattr(places, "snapshot", None)
    if snap is None or not categories or len(geometry) < 2:
        return []
    from app.core.geo import haversine_m

    found, walked = {}, 0.0
    for i, (lat, lon) in enumerate(geometry):
        if i:
            walked += haversine_m(*geometry[i - 1], lat, lon)
        for p in snap.destination.within(lat, lon, SHOP_NEAR_M):
            if p.category in categories and p.id not in found:
                found[p.id] = {"id": p.id, "name": p.name, "category": p.category, "lat": p.lat, "lon": p.lon,
                               "along_m": round(walked, 1)}
    return sorted(found.values(), key=lambda p: p["along_m"])


def kinds_passed(legs: list[RouteLeg], kinds: list[str], pois, places) -> list[str]:
    """Which of the asked-for kinds the real legs pass, from map data only."""
    if not kinds:
        return []
    cats: set[str] = set()
    shore = 0.0
    for leg in legs:
        if pois is not None:
            cats |= pois.categories_along(leg.geometry)
            if "waterfront" in kinds:
                shore += pois.shore_m(leg.geometry)
    out = []
    for k in kinds:
        if k in POI_KINDS:
            hit = bool(cats & set(POI_KINDS[k]))
        elif k == "waterfront":
            hit = shore >= WATERFRONT_MIN_M
        else:  # shops
            hit = any(shops_along(leg.geometry, {SHOP_KINDS[k]}, places) for leg in legs)
        if hit:
            out.append(k)
    return out


def mark_stops(legs: list[RouteLeg], n: int, kinds: list[str], places=None, only: bool = False,
               not_named: str | None = None) -> list[dict]:
    """Up to n stops among the places on the legs (no detour): the kinds asked for first, then the
    rest, spread out, none at the very start or end. Marks them {"stop": k} in the legs' POIs (on
    copies) and returns them in walking order. Fewer when the route passes fewer places.
    With `only` (stops typed as "a coffee", "a bookstore"), stops are of those kinds or none, and
    shops of those kinds right on the route join the legs' POIs. No two stops (nor a stop and the
    walk's end, `not_named`) share a name: two Starbucks are one kind of stop."""
    if n <= 0:
        return []
    wanted = {c for k in kinds for c in POI_KINDS.get(k, ())} | {SHOP_KINDS[k] for k in kinds if k in SHOP_KINDS}
    shops = {SHOP_KINDS[k] for k in kinds if k in SHOP_KINDS}
    if shops and places is not None:
        for li, leg in enumerate(legs):
            extra = [p for p in shops_along(leg.geometry, shops, places) if p["id"] not in {q["id"] for q in leg.pois}]
            if extra:
                legs[li] = leg.model_copy(update={"pois": sorted([*leg.pois, *extra], key=lambda p: p.get("along_m", 0.0))})
    total = sum(leg.distance_m for leg in legs) or 1.0
    found, offset = [], 0.0
    for li, leg in enumerate(legs):
        for p in leg.pois:
            if only and p.get("category") not in wanted:
                continue
            at = offset + p.get("along_m", 0.0)
            if STOP_EDGE_SHARE * total <= at <= (1 - STOP_EDGE_SHARE) * total:
                found.append((li, at, p))
        offset += leg.distance_m
    spacing = total / (n + 1) / 2
    chosen: list[tuple[int, float, dict]] = []
    for li, at, p in sorted(found, key=lambda f: (p_rank(f[2], wanted), f[1])):
        if len(chosen) == n:
            break
        if p.get("name") == not_named:
            continue
        if all(abs(at - c[1]) >= spacing and p["id"] != c[2]["id"] and p.get("name") != c[2].get("name")
               for c in chosen):  # a loop passes some twice
            chosen.append((li, at, p))
    chosen.sort(key=lambda c: c[1])
    ids = {id(c[2]): k for k, c in enumerate(chosen, 1)}
    for li, leg in enumerate(legs):
        legs[li] = leg.model_copy(update={"pois": [{**p, "stop": ids[id(p)]} if id(p) in ids else p
                                                   for p in leg.pois]})
    return [{"stop": k, "id": p["id"], "name": p["name"], "category": p["category"], "lat": p["lat"],
             "lon": p["lon"]} for k, (_, _, p) in enumerate(chosen, 1)]


def p_rank(p: dict, wanted: set[str]) -> int:
    return 0 if p.get("category") in wanted else 1


def describe(passed: list[str], stops: list[dict], asked_stops: int, asked_kinds: list[str] | None = None,
             stop_kinds: list[str] | None = None, avoided: tuple[list[str], list[str]] | None = None) -> str:
    """The plan card's sentence about the options, from what the route really does. `avoided` is
    (places typed under Avoid that the walk keeps away from, those it still passes)."""
    parts = []
    if passed:
        parts.append("Passes " + _join([KIND_LABELS[k] for k in passed]) + ".")
    missed = [k for k in asked_kinds or [] if k not in passed]
    if missed:
        parts.append("Doesn't pass " + _join([KIND_LABELS[k] for k in missed]).replace(" and ", " or ")
                     + ": a wish, not a must.")
    if stops:
        parts.append(f"{len(stops)} stop{'s' if len(stops) > 1 else ''} on the way: "
                     + _join([s["name"] for s in stops]) + ".")
    if asked_stops and len(stops) < asked_stops:
        if stop_kinds:
            kinds = _join([PLURALS.get(k, k.replace("_", " ")) for k in stop_kinds]).replace(" and ", " or ")
            parts.append(f"Only {len(stops)} of the {asked_stops} stops asked for: this route passes fewer {kinds} "
                         "right on the way.")
        else:
            parts.append(f"Only {len(stops)} of the {asked_stops} stops asked for: this route passes fewer places.")
    if avoided:
        clear, near = avoided
        if clear:
            parts.append("Keeps away from " + _join(clear) + ".")
        if near:
            parts.append("Still passes near " + _join(near) + ": no reasonable way around.")
    return " ".join(parts)


def avoided(legs: list[RouteLeg], places_to_avoid) -> tuple[list[str], list[str]] | None:
    """Which of the places typed under Avoid the walk keeps away from, and which it still passes."""
    if not places_to_avoid:
        return None
    from app.services.planner import passed_on

    near = passed_on(legs, places_to_avoid)
    return [p.name for p in places_to_avoid if p.name not in near], near


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
