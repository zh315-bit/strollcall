"""The walking companion: one request during a walk, one tool, a reply built from the tool's result.

Hold to talk (Muse Voice Transcribe) or a quick-tap chip gives the request. For spoken requests
Muse Spark picks the tool and its arguments; a chip names the tool itself and makes no model call.
Muse Spark sees only the words and the whole minutes left: never a position, a place's
coordinates, the route or a place name from our data (privacy test: test_meta_privacy.py).

Tools, all on our own map data:
- add_stop: a cafe, bakery, ice cream shop, bookstore, park or landmark on the way, routed through it
- set_time_left: fit the rest of the walk in N minutes (a nearer end through the solo planner, or
  the way back to a loop's start)
- whats_nearby: up to three places within a short walk (services/nearby.py)
- identify_landmark: the named landmark nearest to the walker, with its sourced intro if we have one
- reroute_avoid: the same target avoiding stairs, busy avenues or transit hubs where the map marks them

Route changes go through the planner's walking graph (local only: no external routing call) and come
back as new legs the walking screen can follow and undo. Replies are templates filled from the
tool's result, so they never say more than the data. Positions are used once, never stored or logged.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.core.config import ROOT_DIR, get_settings, output_cap_override, reasoning_override
from app.core.errors import ProviderError
from app.core.geo import haversine_m
from app.core.hours import is_open
from app.models.schemas import RouteLeg, WalkIntent, WalkOptions

log = logging.getLogger(__name__)

NYC = ZoneInfo("America/New_York")
Point = tuple[float, float]

TOOLS = ["add_stop", "set_time_left", "whats_nearby", "identify_landmark", "reroute_avoid", "none"]
STOP_KINDS = ["cafe", "bakery", "ice_cream", "bookstore", "park", "landmark"]
STOP_LABELS = {"cafe": "coffee", "bakery": "bakery", "ice_cream": "ice cream", "bookstore": "bookstore",
               "park": "park", "landmark": "landmark"}
AVOID_KINDS = ["busy_avenues", "stairs", "transit_hubs"]
AVOID_LABELS = {"busy_avenues": "busy avenues", "stairs": "stairs", "transit_hubs": "major transit hubs"}
CATEGORY_WORDS = {"ice_cream": "ice cream shop", "park_gate": "park gate"}

MAX_STOP_DETOUR_MIN = 15.0  # a stop that adds more than this is not "on the way"
STOP_TRIES = 5  # nearest-by-detour candidates routed for real
LANDMARK_NEAR_M = 120.0  # "what's that?" answers only for a landmark this close
MIN_TIME_LEFT, MAX_TIME_LEFT = 5, 120
INTROS_PATH = ROOT_DIR / "frontend" / "data" / "poi_intros.json"


class WalkState(BaseModel):
    """Where the walk stands, from the walking screen. Nothing here is stored."""
    lat: float = Field(ge=-90, le=90)  # the walker now
    lon: float = Field(ge=-180, le=180)
    target_lat: float = Field(ge=-90, le=90)  # the current leg's end
    target_lon: float = Field(ge=-180, le=180)
    target_name: str = Field(max_length=120)
    target_kind: str = "destination"  # meetup / turnaround / destination
    target_category: str | None = None
    start_lat: float | None = None  # a loop: where the walk returns to
    start_lon: float | None = None
    fixed_target: bool = False  # walking with a friend: never move the meeting point or the shared end
    m_per_min: float = Field(default=80.0, ge=40, le=120)
    minutes_left: float = Field(ge=0, le=300)  # the whole rest of the walk, as the screen shows it
    avoid: list[str] = Field(default=[], max_length=3)
    stops: int = Field(default=0, ge=0, le=9)  # stops already on the route (the next one is numbered after them)


class Choice(BaseModel):
    tool: str
    kind: str | None = None  # add_stop
    place_id: str | None = None  # add_stop for a place from "What's nearby?"
    minutes: int | None = None  # set_time_left
    avoid: str | None = None  # reroute_avoid


class Answer(BaseModel):
    tool: str
    parts: list = []  # the reply: strings, and {"b": name} for a place name shown bold
    legs: list[dict] | None = None  # new legs (a route change), or None; the screen keeps the old ones for Undo
    replace: str = "current"  # the legs replace the current leg only, or "rest": the current leg and all after it
    places: list[dict] = []  # places to mark on the map (whats_nearby)
    chips: list[dict] = []  # follow-ups: {"label", "tool", "args"}
    source: str = "chip"  # chip / meta / mock / rules (the model was unavailable)
    heard: str | None = None  # the words this answers (a transcript)


# ---- Choosing the tool (Muse Spark, or rules when the model is unavailable) ----

CHOOSE_PROMPT = f"""You are the walking buddy in StrollCall, a walking app. Someone is on a walk and said something.
Pick the one tool that does what they asked, with its arguments. You do not answer them yourself: the tool's result is shown.

Tools:
- add_stop: they want to stop somewhere on the way. kind: one of {", ".join(STOP_KINDS)} ("coffee" is cafe, "pastries" bakery, "books" bookstore, "somewhere green" park).
- set_time_left: they have a limited time left, or want the walk shorter or longer. minutes: the whole minutes they have from now ({MIN_TIME_LEFT}-{MAX_TIME_LEFT}).
- whats_nearby: they ask what is around, nearby or worth seeing close by.
- identify_landmark: they ask what a building, statue or place they are looking at is.
- reroute_avoid: they want a different way that avoids something. avoid: one of {", ".join(AVOID_KINDS)}.
- none: anything else, or something no tool can do (safety, crowds, weather, restrooms, directions to another city).

Set arguments a tool does not use to null. Return only JSON matching the schema."""

CHOOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "enum": TOOLS},
        "kind": {"type": ["string", "null"], "enum": STOP_KINDS + [None]},
        "minutes": {"type": ["integer", "null"], "minimum": MIN_TIME_LEFT, "maximum": MAX_TIME_LEFT},
        "avoid": {"type": ["string", "null"], "enum": AVOID_KINDS + [None]},
    },
    "required": ["tool", "kind", "minutes", "avoid"],
    "additionalProperties": False,
}

RULES = [
    (r"\b(coffee|cafe|café|espresso|latte)\b", "add_stop", {"kind": "cafe"}),
    (r"\b(bakery|pastr|croissant|bread)", "add_stop", {"kind": "bakery"}),
    (r"\b(ice ?cream|gelato)\b", "add_stop", {"kind": "ice_cream"}),
    (r"\b(book|bookstore|bookshop)s?\b", "add_stop", {"kind": "bookstore"}),
    (r"\b(park|green|trees)\b.*\b(stop|way|pass)|\b(stop|way|pass)\b.*\b(park|green)\b", "add_stop", {"kind": "park"}),
    (r"\b(\d{1,3})\s*(min|minute)", "set_time_left", {}),
    (r"\b(what'?s|what is) (that|this)\b|\bwhat am i looking at\b", "identify_landmark", {}),
    (r"\b(nearby|near me|around here|around me|close by|worth seeing)\b", "whats_nearby", {}),
    (r"\b(avoid|no|without)\b.*\bstairs?\b", "reroute_avoid", {"avoid": "stairs"}),
    (r"\b(avoid|away from|quieter|no)\b.*\b(avenue|traffic|busy|main road)", "reroute_avoid", {"avoid": "busy_avenues"}),
    (r"\b(avoid|away from)\b.*\b(station|hub|transit|subway)", "reroute_avoid", {"avoid": "transit_hubs"}),
]


def choose_by_rules(text: str) -> Choice:
    t = text.lower()
    for pattern, tool, args in RULES:
        m = re.search(pattern, t)
        if m:
            if tool == "set_time_left":
                return Choice(tool=tool, minutes=max(MIN_TIME_LEFT, min(MAX_TIME_LEFT, int(m.group(1)))))
            return Choice(tool=tool, **args)
    return Choice(tool="none")


def choose(text: str, minutes_left: float) -> tuple[Choice, str]:
    """The tool for what they said, and who chose it (meta / mock / rules)."""
    from app.providers import meta_or_mock

    user = f"Minutes left on this walk: {round(minutes_left)}\nThey said: {text}"
    cap = output_cap_override.set(512)  # a few short fields
    effort = reasoning_override.set(get_settings().accept_reasoning_effort)  # they're waiting, mid-walk
    try:
        data, source = meta_or_mock(lambda m: m.structured_json(CHOOSE_PROMPT, user, CHOOSE_SCHEMA, name="companion_tool"))
        choice = Choice(tool=data.get("tool") if data.get("tool") in TOOLS else "none", kind=data.get("kind"),
                        minutes=data.get("minutes"), avoid=data.get("avoid"))
        return _checked(choice), source
    except (ProviderError, ValueError) as e:
        log.warning("companion: tool choice fell back to rules (%s)", getattr(e, "code", type(e).__name__))
        return choose_by_rules(text), "rules"
    finally:
        output_cap_override.reset(cap)
        reasoning_override.reset(effort)


def _checked(c: Choice) -> Choice:
    """Arguments outside what each tool accepts make it ask again rather than guess."""
    if c.tool == "add_stop" and c.kind not in STOP_KINDS and not c.place_id:
        return Choice(tool="none")
    if c.tool == "set_time_left" and not (isinstance(c.minutes, int) and MIN_TIME_LEFT <= c.minutes <= MAX_TIME_LEFT):
        return Choice(tool="none")
    if c.tool == "reroute_avoid" and c.avoid not in AVOID_KINDS:
        return Choice(tool="none")
    return c


# ---- Running a tool ----

def run(choice: Choice, s: WalkState, now: datetime | None = None, said: str | None = None) -> Answer:
    choice = _checked(choice)
    now = now or datetime.now(NYC)
    if choice.tool == "none":
        return Answer(tool="none", parts=["I can add a stop on the way, fit the walk into the time you have, show "
                                          "what's nearby, name a landmark you're looking at, or find a way that "
                                          "avoids stairs or busy avenues."], chips=default_chips())
    try:
        if choice.tool == "add_stop":
            return add_stop(choice.kind, s, now, place_id=choice.place_id)
        if choice.tool == "set_time_left":
            return set_time_left(choice.minutes, s, now)
        if choice.tool == "whats_nearby":
            return whats_nearby(s, now)
        if choice.tool == "identify_landmark":
            return identify_landmark(s, said)
        return reroute_avoid(choice.avoid, s)
    except OutsideArea:
        return Answer(tool=choice.tool, parts=["You're outside the area our walking map covers, so I can't change "
                                               "the route from here."])
    except ProviderError as e:
        log.warning("companion: %s failed (%s)", choice.tool, e.code)
        return Answer(tool=choice.tool, parts=["I couldn't work that out on the map just now. Your route is "
                                               "unchanged."])


def default_chips() -> list[dict]:
    return [{"label": "I have 10 min", "tool": "set_time_left", "args": {"minutes": 10}},
            {"label": "What's nearby?", "tool": "whats_nearby", "args": {}}]


class OutsideArea(Exception):
    pass


def _routing(s: WalkState, avoid: list[str] | None = None):
    """The planner's walking graph at this walker's pace (and avoiding what they asked), local only."""
    from app.providers import get_routing
    from app.services.options import PACE_M_PER_MIN, routing_view

    routing = get_routing()
    if not hasattr(routing, "graph"):
        raise ProviderError("routing_unavailable", "the companion needs the local walking map")
    for p in ((s.lat, s.lon), (s.target_lat, s.target_lon)):
        try:
            routing.graph.snap(p)
        except Exception as e:  # OutsideCoverage: never fall back to an external router mid-walk
            raise OutsideArea() from e
    pace = min(PACE_M_PER_MIN, key=lambda k: abs(PACE_M_PER_MIN[k] - s.m_per_min))
    wanted = [a for a in (avoid if avoid is not None else s.avoid) if a in AVOID_KINDS]
    return routing_view(routing, WalkOptions(pace=pace, avoid=wanted))


def _here(s: WalkState) -> Point:
    return (s.lat, s.lon)


def _target(s: WalkState) -> Point:
    return (s.target_lat, s.target_lon)


def _leg_dict(leg: RouteLeg, s: WalkState, **over) -> dict:
    """A leg as the walking screen follows it (walk.js WalkFollower)."""
    d = {"name": s.target_name, "kind": s.target_kind, "target": [s.target_lat, s.target_lon],
         "category": s.target_category, "geometry": [list(p) for p in leg.geometry], "steps": leg.steps,
         "pois": leg.pois, "minutes": round(leg.duration_min, 1)}
    d.update(over)
    return d


def _join(a: RouteLeg, b: RouteLeg) -> RouteLeg:
    """Two legs walked one after the other, as one (steps and POIs measured from the start)."""
    shift = a.distance_m
    steps = a.steps + [{**st, "along_m": round(st.get("along_m", 0.0) + shift, 1)} for st in b.steps
                       if st.get("kind") != "depart"]
    pois = a.pois + [{**p, "along_m": round(p.get("along_m", 0.0) + shift, 1)} for p in b.pois]
    return RouteLeg(geometry=a.geometry + b.geometry[1:], distance_m=a.distance_m + b.distance_m,
                    duration_min=a.duration_min + b.duration_min, steps=steps, pois=pois)


def _category(c: str | None) -> str:
    return CATEGORY_WORDS.get(c or "", (c or "place").replace("_", " "))


def _mins(x: float) -> str:
    n = max(1, round(x))
    return f"{n} minute" if n == 1 else f"{n} minutes"


def _hours(place, at: datetime) -> str:
    state = is_open(place.opening_hours, at)
    if state is True:
        return "open when you get there, per OpenStreetMap"
    if state is None:
        return "opening hours unknown"
    return "closed then per OpenStreetMap"


def add_stop(kind: str | None, s: WalkState, now: datetime, place_id: str | None = None) -> Answer:
    from app.providers import get_places

    routing = _routing(s)
    here, there = _here(s), _target(s)
    base = routing.walk(here, there)
    places = get_places()
    if place_id:  # a place from "What's nearby?": look it up again, never trust a name from the page
        found = _place_by_id(place_id, here)
        if found is None:
            return Answer(tool="add_stop", parts=["I couldn't find that place in our map data any more."])
        candidates, kind = [found], found.category
    else:
        mid = ((here[0] + there[0]) / 2, (here[1] + there[1]) / 2)
        radius = min(haversine_m(*here, *there) / 2 + 300, 1500)
        candidates = [p for p in places.destination_candidates(*mid, radius, [kind]) if p.category == kind]
    eta = lambda p: now + timedelta(minutes=haversine_m(*here, p.lat, p.lon) * 1.3 / s.m_per_min)  # noqa: E731
    candidates = [p for p in candidates if is_open(p.opening_hours, eta(p)) is not False]
    if not candidates:
        return Answer(tool="add_stop", parts=[f"I couldn't find an open {STOP_LABELS.get(kind, _category(kind))} "
                                              "near your route in our map data."], chips=default_chips())
    direct = haversine_m(*here, *there)
    candidates.sort(key=lambda p: (is_open(p.opening_hours, eta(p)) is not True,
                                   haversine_m(*here, p.lat, p.lon) + haversine_m(p.lat, p.lon, *there) - direct, p.id))
    best = None
    for p in candidates[:STOP_TRIES]:
        try:
            joined = _join(routing.walk(here, (p.lat, p.lon)), routing.walk((p.lat, p.lon), there))
        except ProviderError:
            continue
        if best is None or joined.duration_min < best[1].duration_min:
            best = (p, joined)
    if best is None:
        return Answer(tool="add_stop", parts=["I couldn't route a stop on the way just now. Your route is unchanged."])
    p, joined = best
    added = joined.duration_min - base.duration_min
    if added > MAX_STOP_DETOUR_MIN and not place_id:
        return Answer(tool="add_stop", parts=["The nearest ", {"b": p.name}, f" would add {_mins(added)}, so I left "
                                              "your route as it is."], chips=default_chips())
    n = s.stops + 1
    stop = {"id": p.id, "name": p.name, "category": _category(p.category), "lat": p.lat, "lon": p.lon,
            "along_m": round(routing.walk(here, (p.lat, p.lon)).distance_m, 1), "stop": n}
    joined = joined.model_copy(update={"pois": [stop] + [q for q in joined.pois if q.get("id") != p.id]})
    more = f"That's {round(added)} more minute{'s' if round(added) != 1 else ''}." if added >= 0.5 else "It's on your way: no extra time."
    label = STOP_LABELS.get(kind, _category(kind))
    return Answer(tool="add_stop", legs=[_leg_dict(joined, s, stops=[stop])],
                  parts=[f"Added a {label} stop: ", {"b": p.name}, f", {_hours(p, eta(p))}. {more}"])


def set_time_left(minutes: int | None, s: WalkState, now: datetime) -> Answer:
    left = round(s.minutes_left)
    if s.minutes_left <= minutes + 1:
        return Answer(tool="set_time_left", parts=[f"You're fine: about {_mins(s.minutes_left)} left, within your "
                                                   f"{minutes}."])
    if s.fixed_target:
        return Answer(tool="set_time_left", parts=[f"This walk has about {_mins(s.minutes_left)} left, and your friend "
                                                   "is walking to ", {"b": s.target_name}, " too, so I've kept the plan. "
                                                   "End the walk any time; the Open in a map app button gives you the "
                                                   "quickest way."])
    routing = _routing(s)
    here = _here(s)
    if s.start_lat is not None and s.start_lon is not None:  # a loop: head back now
        back = routing.walk(here, (s.start_lat, s.start_lon))
        leg = _leg_dict(back, s, name="your start", kind="destination", target=[s.start_lat, s.start_lon], category=None)
        fits = "" if back.duration_min <= minutes + 1 else " That's the quickest way, a little over your time."
        return Answer(tool="set_time_left", legs=[leg], replace="rest",
                      parts=[f"Heading back to your start now: about {_mins(back.duration_min)} instead of {left}.{fits}"])
    plan = _shorter_walk(here, minutes, s, routing, now)
    if plan is None:
        return Answer(tool="set_time_left", parts=[f"I couldn't find another {_category(s.target_category)} within "
                                                   f"{minutes} minutes in our map data, so the route stays. ",
                                                   {"b": s.target_name}, f" is about {_mins(s.minutes_left)} away."])
    place, leg = plan
    new = _leg_dict(leg, s, name=place.name, target=[place.lat, place.lon], category=place.category, id=place.id,
                    kind="destination")
    return Answer(tool="set_time_left", legs=[new], replace="rest",
                  parts=["New end: ", {"b": place.name}, f" ({_category(place.category)}, {_hours(place, now + timedelta(minutes=leg.duration_min))}), "
                         f"about {_mins(leg.duration_min)} from here instead of {left}."])


def _shorter_walk(here: Point, minutes: int, s: WalkState, routing, now: datetime):
    """The solo planner's best walk from here within `minutes`, ending at the same kind of place."""
    from app.providers import get_places
    from app.services.planner import DESTINATION_TYPES, Weights
    from app.services.solo import _plan

    kind = s.target_category if s.target_category in DESTINATION_TYPES else None
    # model_construct: the planner's own 15-60 min bounds are for planning a walk, not for its last few minutes.
    intent = WalkIntent.model_construct(duration_min=minutes, duration_strict=True, vibes=[], endpoint_type=kind,
                                        avoid=[], hard_constraints=[])
    plan = _plan(here, intent, get_places(), routing, now, None, Weights.from_settings())
    if plan.status != "proposed":
        return None
    c = plan.candidates[0]
    return plan.places[c.destination_place_id], c.leg


def whats_nearby(s: WalkState, now: datetime) -> Answer:
    from app.services.nearby import highlights

    found, _ = highlights(_here(s), now, limit=3)
    if not found:
        return Answer(tool="whats_nearby", parts=["I don't see a named park, landmark or open cafe within about 15 "
                                                  "minutes' walk in our map data."])
    parts: list = ["Close by: "]
    for i, h in enumerate(found):
        if i:
            parts.append(", " if i < len(found) - 1 else " and ")
        open_note = ", open now per OpenStreetMap" if h.kind == "cafe" and h.open_now else ""
        parts += [{"b": h.name}, f" ({_category(h.category)}{open_note}, {_mins(h.walk_min)})"]
    parts.append(".")
    chips = [{"label": f"Stop at {h.name}"[:40], "tool": "add_stop", "args": {"place_id": h.id}} for h in found
             if h.kind == "cafe" or h.kind == "park"][:2]
    return Answer(tool="whats_nearby", parts=parts, chips=chips,
                  places=[{"id": h.id, "name": h.name, "category": h.category, "lat": h.lat, "lon": h.lon,
                           "walk_min": h.walk_min} for h in found])


@lru_cache(maxsize=1)
def _intros() -> dict:
    try:
        return json.loads(INTROS_PATH.read_text()).get("intros", {})
    except (OSError, ValueError):
        return {}


STOPWORDS = {"what", "that", "this", "there", "here", "building", "place", "thing", "called", "big", "tall", "with",
             "the", "over", "right", "left", "front", "looking", "look", "which", "whats", "is"}


# What people call it -> our POI categories (providers/route_pois.py)
KIND_WORDS = {"statue": {"artwork", "memorial"}, "sculpture": {"artwork"}, "mural": {"artwork"}, "art": {"artwork"},
              "monument": {"memorial", "landmark"}, "tower": {"notable", "landmark"}, "church": {"notable", "historic"}}


def _words(text: str | None) -> set[str]:
    words = {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in STOPWORDS}
    return words.union(*(KIND_WORDS.get(w, set()) for w in words))


def identify_landmark(s: WalkState, said: str | None = None) -> Answer:
    """The nearest named landmark; one whose name has a word they used ("the arch") wins within reach."""
    from app.providers import get_routing
    from app.services.nearby import LANDMARK_KINDS

    pois = getattr(get_routing(), "pois", None)
    here = _here(s)
    words, best = _words(said), None
    for p in (pois.pois if pois else []):
        if p["category"] not in LANDMARK_KINDS and p["category"] not in ("park", "garden"):
            continue
        d = min(haversine_m(*here, a, b) for a, b in p["pts"])
        named = bool(words & _words(p["name"] + " " + p["category"]))
        if d <= LANDMARK_NEAR_M * (2 if named else 1) and (best is None or (not named, d) < (not best[2], best[0])):
            best = (d, p, named)
    if best is None:
        return Answer(tool="identify_landmark", parts=[f"I can't find a named landmark within about "
                                                       f"{LANDMARK_NEAR_M:.0f} m of you in our map data."])
    d, p, _ = best
    parts = ["That's probably ", {"b": p["name"]}, f", {'an' if _category(p['category'])[0] in 'aeiou' else 'a'} "
             f"{_category(p['category'])} about {max(10, round(d / 10) * 10):.0f} m from you (OpenStreetMap)."]
    intro = _intros().get(p["id"])
    if intro:
        first = re.split(r"(?<=[.!?])\s", intro["intro"].strip(), maxsplit=1)[0]
        parts.append(f" {first} (Wikipedia, CC BY-SA)")
    return Answer(tool="identify_landmark", parts=parts)


def reroute_avoid(avoid: str | None, s: WalkState) -> Answer:
    from app.providers.local_routing import AVOID_FLAGS

    label = AVOID_LABELS[avoid]
    graph = getattr(_routing(s), "graph", None)
    flags = getattr(graph, "edge_flags", None)
    if flags is None or not (flags & AVOID_FLAGS[avoid]).any():
        return Answer(tool="reroute_avoid", parts=[f"Our map here doesn't mark {label}, so I can't route around them. "
                                                   "Your route is unchanged."])
    wanted = list(dict.fromkeys([*s.avoid, avoid]))
    before = _routing(s).walk(_here(s), _target(s))
    after = _routing(s, wanted).walk(_here(s), _target(s))
    if [tuple(p) for p in after.geometry] == [tuple(p) for p in before.geometry]:
        return Answer(tool="reroute_avoid", parts=[f"Your route already avoids {label} where the map marks them."])
    diff = after.duration_min - before.duration_min
    more = f"{_mins(diff)} longer" if diff >= 0.5 else "about the same time"
    return Answer(tool="reroute_avoid", legs=[_leg_dict(after, s, avoid=wanted)],
                  parts=[f"New way avoiding {label} where the map marks them: {more}. Map data can miss some."])


def _place_by_id(place_id: str, near: Point):
    from app.providers import get_places, get_routing

    places = get_places()
    for p in places.destination_candidates(*near, 1500, STOP_KINDS):
        if p.id == place_id:
            return p
    pois = getattr(get_routing(), "pois", None)
    for p in (pois.pois if pois else []):
        if p["id"] == place_id:
            from app.models.schemas import Place

            lat, lon = min(((a, b) for a, b in p["pts"]), key=lambda q: haversine_m(*near, *q))
            return Place(id=p["id"], name=p["name"], lat=lat, lon=lon, category=p["category"])
    return None


def ask(text: str | None, choice: Choice | None, s: WalkState, now: datetime | None = None) -> Answer:
    """A chip's tool, or the tool Muse Spark picks for what they said; then the tool."""
    if choice is not None:
        return run(choice, s, now)
    chosen, source = choose(text or "", s.minutes_left)
    answer = run(chosen, s, now, said=text)
    return answer.model_copy(update={"source": source, "heard": text})
