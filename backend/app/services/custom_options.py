""""Something else" under Pass by, Avoid and Stops on the way: typed words turned into what the
planner can honor with map data.

Muse Spark reads the words only (no position, no place from our data) and answers with kinds from a
fixed list per field, place names as the person wrote them, a number of stops, and what it could not
map ("hills", "well lit"). Place names are then looked up in our own data (route POIs and the place
snapshot), so a place is only ever one we have, by id. Without the model (budget guard, mock, an
error) keyword rules do the same, more narrowly.

What each field becomes (services/options.py):
- pass: more "Pass by" kinds (bridges, viewpoints, fountains, squares, cafes, bakeries, ice cream)
  and named places to pass, both soft preferences
- avoid: stairs, busy avenues or transit hubs (map flags), and named places whose surroundings get a
  routing penalty
- stops: how many stops and of which kinds; stops typed this way are of those kinds or none. A
  named place to stop at is passed by instead (the page sends it with the Pass by places): it may
  not be right on the way
Anything else (hills, lighting, safety, crowds as such, restrooms) has no map data: the answer says
so instead of pretending.
"""

import logging
import re
import threading
from collections import OrderedDict
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

from app.core.config import get_settings, output_cap_override, reasoning_override
from app.core.errors import ProviderError
from app.core.geo import haversine_m
from app.models.schemas import PASS_KIND_NAMES

log = logging.getLogger(__name__)

Field = Literal["pass", "avoid", "stops"]
AVOID_KINDS = ("stairs", "busy_avenues", "transit_hubs")
STOP_KINDS = tuple(k for k in PASS_KIND_NAMES if k != "waterfront")
KINDS = {"pass": PASS_KIND_NAMES, "avoid": AVOID_KINDS, "stops": STOP_KINDS}
LABELS = {"parks": "parks", "waterfront": "the waterfront", "landmarks": "landmarks", "public_art": "public art",
          "bookstores": "bookstores", "markets": "markets", "bridges": "bridges", "viewpoints": "viewpoints",
          "fountains": "fountains", "squares": "squares", "cafes": "cafes", "bakeries": "bakeries",
          "ice_cream": "ice cream", "stairs": "stairs", "busy_avenues": "busy avenues",
          "transit_hubs": "major transit hubs"}
MAX_TEXT = 80
MAX_PLACES = 3

FIELD_HELP = {
    "pass": "places or kinds of places they would like the walk to pass by",
    "avoid": "things or places they would like the walk to stay away from",
    "stops": "stops they would like to make on the way",
}
HINTS = {
    "pass": '"coffee" is cafes, "green" or "trees" parks, "the river" waterfront, "murals" public_art, '
            '"old buildings" landmarks, "a nice view" viewpoints',
    "avoid": '"steps" is stairs, "traffic", "big roads" or "noise" busy_avenues, "big stations" transit_hubs; '
             'a named station (Penn Station, Grand Central) is transit_hubs and also a place',
    "stops": '"a coffee" is cafes, "pastries" bakeries, "gelato" ice_cream, "books" bookstores, '
             '"somewhere green" parks, "a photo spot" viewpoints',
}


def _prompt(field: Field) -> str:
    return f"""You read a short note someone typed in StrollCall, a walking app in New York City: {FIELD_HELP[field]}.
Turn it into what the route planner understands. Never invent anything the note does not say.

- kinds: any of {", ".join(KINDS[field])} that the note asks for ({HINTS[field]}).
- places: specific named places in the note, written as they wrote them ("Brooklyn Bridge", "Times Square"). Not kinds.
- count: {"how many stops they want, 1-3 (one per kind or place they list when they give no number)" if field == "stops" else "null"}.
- unsupported: short words for what they ask that is neither a kind above nor a named place (hills, lighting, safety, crowds, shade, restrooms, construction).

Return only JSON matching the schema."""


def _schema(field: Field) -> dict:
    return {
        "type": "object",
        "properties": {
            "kinds": {"type": "array", "items": {"type": "string", "enum": list(KINDS[field])}, "maxItems": 4},
            "places": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_PLACES},
            "count": {"type": ["integer", "null"], "minimum": 1, "maximum": 3},
            "unsupported": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        },
        "required": ["kinds", "places", "count", "unsupported"],
        "additionalProperties": False,
    }


class Understood(BaseModel):
    field: Field
    text: str
    kinds: list[str] = []
    places: list[dict] = []  # [{id, name}] from our data
    count: int = 0  # stops only
    labels: list[str] = []  # what was understood, for the page: kinds then place names
    unsupported: list[str] = []
    missing: list[str] = []  # place names typed that our map does not have
    note: str = ""
    source: str = "rules"


# ---- Keyword rules (no model) ----

RULES = {
    "pass": [(r"\bparks?\b|\bgreen\b|\btrees\b|\bgardens?\b", "parks"),
             (r"\bwater(front)?\b|\briver\b|\bharbou?r\b|\bpiers?\b|\besplanade\b", "waterfront"),
             (r"\blandmarks?\b|\bhistoric\b|\bmonuments?\b|\bmemorials?\b|\barchitecture\b|\bold buildings\b", "landmarks"),
             (r"\bmurals?\b|\bsculptures?\b|\bstatues?\b|\bstreet art\b|\bpublic art\b|\bart\b", "public_art"),
             (r"\bbooks?(stores?|shops?)?\b", "bookstores"), (r"\bmarkets?\b", "markets"),
             (r"\bbridges?\b", "bridges"), (r"\bviews?\b|\bviewpoints?\b|\blookouts?\b|\bscenic\b", "viewpoints"),
             (r"\bfountains?\b", "fountains"), (r"\bsquares?\b|\bplazas?\b", "squares"),
             (r"\bcoffees?\b|\bcaf[eé]s?\b|\bespressos?\b|\blattes?\b", "cafes"), (r"\bbaker(y|ies)\b|\bpastr", "bakeries"),
             (r"\bice ?cream\b|\bgelato\b", "ice_cream")],
    "avoid": [(r"\bstairs?\b|\bsteps\b", "stairs"),
              (r"\btraffic\b|\bbusy\b|\bavenues?\b|\bbig roads?\b|\bmain roads?\b|\bnois[ey]\b|\bloud\b|\bcars?\b",
               "busy_avenues"),
              (r"\bstations?\b|\btransit\b|\bhubs?\b|\bterminals?\b", "transit_hubs")],
}
RULES["stops"] = [(p, k) for p, k in RULES["pass"] if k != "waterfront"]
NO_DATA = [(r"\bhills?\b|\bhilly\b|\bsteep\b|\bslopes?\b", "hills"), (r"\bdark\b|\blit\b|\blighting\b|\bnight\b", "lighting"),
           (r"\bsafe(ty)?\b|\bunsafe\b|\bsketchy\b", "safety"), (r"\bcrowd(s|ed)?\b|\btourists?\b", "crowds"),
           (r"\bshade\b|\bshady\b|\bsun(ny)?\b", "shade"), (r"\brest ?rooms?\b|\btoilets?\b|\bbathrooms?\b", "restrooms"),
           (r"\bconstruction\b|\bscaffold", "construction"), (r"\brain\b|\bweather\b|\bwind\b", "weather")]
NUMBERS = {"one": 1, "two": 2, "three": 3, "a": 1, "an": 1}
FILLER = re.compile(r"^(please |i'?d like to |i want to |let'?s |maybe )?(pass( by)?|go (by|past|through)|see|visit|"
                    r"avoid|skip|stay away from|not|no|stop at|a stop at|near|around|through|the)\s+", re.I)


def by_rules(field: Field, text: str, origin=None) -> dict:
    """Each part of the note ("Times Square, hills") is a place when our data has one by exactly
    that name, else the kinds and no-data words it mentions."""
    t = text.lower()
    kinds, unsupported, places = [], [], []
    for part in re.split(r",|;|\band\b|&|\+|/", text):
        name = part.strip(" .!?")
        while (cut := FILLER.sub("", name)) != name:
            name = cut
        if len(name) >= 3 and find_place(name, origin, exact=True):
            places.append(name)
            continue
        low = part.lower()
        kinds += [k for p, k in RULES[field] if re.search(p, low) and k not in kinds]
        unsupported += [w for p, w in NO_DATA if re.search(p, low) and w not in unsupported]
    count = None
    if field == "stops":
        m = re.search(r"\b(one|two|three|[123])\b", t)
        count = (NUMBERS.get(m.group(1)) or int(m.group(1))) if m else max(1, len(kinds) + len(places))
    return {"kinds": kinds, "places": places, "count": count, "unsupported": unsupported}


# ---- The model ----

_cache: OrderedDict[tuple[str, str], tuple[dict, str]] = OrderedDict()
_cache_lock = threading.Lock()


def read_words(field: Field, text: str, origin=None) -> tuple[dict, str]:
    """What the words ask for, and who read them (meta / spark_open / rules)."""
    from app.providers import meta_or_mock

    key = (field, " ".join(text.lower().split()))
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    cap = output_cap_override.set(1024)  # a few short fields, and room for the model's reasoning
    effort = reasoning_override.set(get_settings().accept_reasoning_effort)  # someone is waiting on the page
    try:
        data, source = meta_or_mock(lambda m: m.structured_json(_prompt(field), f"They typed: {text}", _schema(field),
                                                                name="custom_option"))
        if source == "mock":  # the mock's one fixed answer would ignore the words
            return by_rules(field, text, origin), "rules"
    except (ProviderError, ValueError) as e:
        log.warning("custom option: fell back to rules (%s)", getattr(e, "code", type(e).__name__))
        return by_rules(field, text, origin), "rules"
    finally:
        output_cap_override.reset(cap)
        reasoning_override.reset(effort)
    with _cache_lock:
        _cache[key] = (data, source)
        if len(_cache) > 256:
            _cache.popitem(last=False)
    return data, source


# ---- Places from our data ----

def _norm(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", s.lower().replace("’", "'").replace("'s", "s"))
    return " ".join(w for w in s.split() if w != "the")


@lru_cache(maxsize=1)
def _index() -> list[tuple[str, str, str, float, float, bool]]:
    """(normalized name, id, name, lat, lon, has a Wikipedia page) for every named place we have."""
    from app.providers import get_places, get_routing

    out, seen = [], set()
    try:
        pois = getattr(get_routing(), "pois", None)
    except ProviderError:
        pois = None
    for p in (pois.pois if pois else []):
        if p.get("name") and p["id"] not in seen:
            seen.add(p["id"])
            out.append((_norm(p["name"]), p["id"], p["name"], p["lat"], p["lon"], bool(p.get("wikipedia"))))
    try:
        snap = getattr(get_places(), "snapshot", None)
    except ProviderError:
        snap = None
    if snap is not None:
        for index in (snap.destination, snap.meetup):
            for c in index.places:
                if c.name and c.id not in seen:
                    seen.add(c.id)
                    out.append((_norm(c.name), c.id, c.name, c.lat, c.lon, False))
    return out


def find_place(name: str, origin=None, exact: bool = False) -> dict | None:
    """The place in our data best matching a typed name: an exact name first, then the one containing
    it with the fewest other words (one with a Wikipedia page first); of several with the same name
    (a chain), the nearest to the start."""
    q = _norm(name)
    if len(q) < 3:
        return None
    word = re.compile(rf"\b{re.escape(q)}\b")
    best = []
    for n, pid, pname, lat, lon, wiki in _index():
        rank = 0 if n == q else 1 if not exact and len(q) >= 4 and word.search(n) else None
        if rank is None:
            continue
        far = haversine_m(origin[0], origin[1], lat, lon) if origin else 0.0
        best.append((rank, len(n.split()) - len(q.split()), not wiki, far, len(n), pid, pname))
    if not best:
        return None
    best.sort()
    return {"id": best[0][-2], "name": best[0][-1]}


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def understand(field: Field, text: str, origin=None) -> Understood:
    text = " ".join(text.split())[:MAX_TEXT]
    data, source = read_words(field, text, origin)
    kinds = [k for k in dict.fromkeys(data.get("kinds") or []) if k in KINDS[field]]
    places, missing = [], []
    for name in [str(n) for n in (data.get("places") or [])][:MAX_PLACES]:
        hit = find_place(name, origin)
        if hit and hit["id"] not in {p["id"] for p in places}:
            places.append(hit)
        elif not hit:
            missing.append(name)
    unsupported = [str(u)[:30] for u in (data.get("unsupported") or [])][:3]
    notes = []
    if field == "avoid" and any("crowd" in u.lower() for u in unsupported):
        # No crowd data: major transit hubs are the nearest thing the map has (as the wish reading does).
        unsupported = [u for u in unsupported if "crowd" not in u.lower()]
        if "transit_hubs" not in kinds:
            kinds.append("transit_hubs")
        notes.append("No crowd data: avoiding major transit hubs is the closest the map can do.")
    count = 0
    if field == "stops" and (kinds or places):
        c = data.get("count")
        count = c if isinstance(c, int) and 1 <= c <= 3 else min(3, max(1, len(kinds)))
    if missing:
        notes.append("Couldn't find " + _join([f"“{m}”" for m in missing]) + " on our map.")
    if unsupported:
        notes.append("No map data for " + _join(unsupported) + ", so the route can't plan for "
                     + ("it." if len(unsupported) == 1 else "them."))
    if not kinds and not places and not notes:
        notes.append("Nothing in that the map can plan with.")
    return Understood(field=field, text=text, kinds=kinds, places=places, count=count,
                      labels=[LABELS[k] for k in kinds] + [p["name"] for p in places],
                      unsupported=unsupported, missing=missing, note=" ".join(notes), source=source)
