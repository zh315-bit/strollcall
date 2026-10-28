"""Free-text wishes -> checkable place requirements (Muse Spark), with a keyword baseline.

People say things like "somewhere we can sit outside", "I'll have my laptop" or "I don't eat
animal products". Muse Spark maps each wish to one item of a fixed menu of requirements that
OpenStreetMap tags can check, and must quote the person's own words for it; quotes that are
not in the text are dropped. Requirements only change the preference fit (soft); they never
add or relax a hard constraint. When a tag is missing the result is "unknown", never "yes".
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from app.core.errors import ProviderError
from app.models.schemas import Place
from app.providers import meta_or_mock

log = logging.getLogger(__name__)

FOOD_AND_BOOKS = ("cafe", "bakery", "ice_cream", "bookstore")


def _tag_check(key: str, yes: tuple[str, ...], no: tuple[str, ...] = ("no",)) -> Callable[[Place], bool | None]:
    def check(p: Place) -> bool | None:
        value = p.tags.get(key)
        if value in yes:
            return True
        if value in no:
            return False
        return None
    return check


def _not_a_chain(p: Place) -> bool | None:
    if p.category not in FOOD_AND_BOOKS:
        return None
    return "brand" not in p.tags  # NYC chains carry OSM brand tags; no brand = not a known chain


@dataclass(frozen=True)
class Requirement:
    key: str
    description: str  # shown to the model and in explanations
    target: str  # destination / meetup
    check: Callable[[Place], bool | None]


REQUIREMENTS = {r.key: r for r in [
    Requirement("outdoor_seating", "destination has outdoor seating (OSM outdoor_seating)", "destination",
                _tag_check("outdoor_seating", ("yes", "sidewalk", "pedestrian_zone", "garden", "patio", "veranda"))),
    Requirement("not_a_chain", "destination is not a chain (no brand in OSM)", "destination", _not_a_chain),
    Requirement("wifi", "destination has wifi / internet access (OSM internet_access)", "destination",
                _tag_check("internet_access", ("yes", "wlan", "wifi", "terminal", "wired"))),
    Requirement("wheelchair_access", "destination is wheelchair accessible (OSM wheelchair=yes)", "destination",
                _tag_check("wheelchair", ("yes", "designated"), ("no", "limited"))),
    Requirement("vegan_options", "destination has vegan options (OSM diet:vegan)", "destination",
                _tag_check("diet:vegan", ("yes", "only"))),
    Requirement("vegetarian_options", "destination has vegetarian options (OSM diet:vegetarian or vegan)",
                "destination", lambda p: _tag_check("diet:vegetarian", ("yes", "only"))(p)
                or _tag_check("diet:vegan", ("yes", "only"))(p)),
    Requirement("indoor_seating", "destination has indoor seating (OSM indoor_seating)", "destination",
                _tag_check("indoor_seating", ("yes",))),
    Requirement("green_meetup", "meet in or at the edge of a park", "meetup",
                lambda p: p.category in ("park", "park_gate")),
    Requirement("viewpoint", "a viewpoint at the meetup point or destination (OSM tourism=viewpoint)", "either",
                lambda p: True if p.tags.get("tourism") == "viewpoint" else None),
]}
UNKNOWN_SCORE = 0.3  # a missing tag counts a little: the place may still have it


class Wish(BaseModel):
    requirement: str
    who: str  # A / B
    quote: str  # the person's own words


class Wishes(BaseModel):
    items: list[Wish] = []
    source: str  # meta / mock / default / keywords
    note: str | None = None

    def for_person(self, who: str) -> list[Wish]:
        return [w for w in self.items if w.who == who]


def requirement_status(wish: Wish, meetup: Place, destination: Place) -> bool | None:
    req = REQUIREMENTS[wish.requirement]
    places = {"destination": [destination], "meetup": [meetup], "either": [meetup, destination]}[req.target]
    results = [req.check(p) for p in places]
    if any(r is True for r in results):
        return True
    if results and all(r is False for r in results):
        return False
    return None


def requirement_score(wish: Wish, meetup: Place, destination: Place) -> float:
    status = requirement_status(wish, meetup, destination)
    return 1.0 if status is True else 0.0 if status is False else UNKNOWN_SCORE


# --- Muse Spark ---

PROMPT = """You map two friends' free-text wishes for a walk to a fixed menu of place requirements
that StrollCall can check in OpenStreetMap data.

Rules:
- Use only requirement keys from the menu. If a wish does not fit any key, leave it out.
- For each item give who said it ("A" or "B") and quote that person's exact words that express it.
- Include implied wishes when the words clearly imply them, e.g. a person who will work on a
  laptop needs wifi; a person who eats no animal products needs vegan options.
- Do not add wishes nobody expressed. Walk length, destination type and vibes are handled elsewhere;
  do not repeat them as requirements.
Return only JSON matching the schema."""


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "wishes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement": {"type": "string", "enum": list(REQUIREMENTS)},
                        "who": {"type": "string", "enum": ["A", "B"]},
                        "quote": {"type": "string"},
                    },
                    "required": ["requirement", "who", "quote"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["wishes"],
        "additionalProperties": False,
    }


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("’", "'")).strip(" .,!")


def interpret_wishes(a_text: str, b_text: str) -> Wishes:
    texts = {"A": a_text.strip(), "B": b_text.strip()}
    if not any(texts.values()):
        return Wishes(source="default", note="no text")
    menu = {k: r.description for k, r in REQUIREMENTS.items()}
    user = json.dumps({"A": texts["A"], "B": texts["B"], "menu": menu})
    try:
        data, source = meta_or_mock(lambda meta: meta.structured_json(PROMPT, user, _schema(), name="wishes"))
    except ProviderError as e:
        log.warning("wishes: Muse Spark unavailable (%s); no requirements", e.code)
        return Wishes(source="default", note=e.code)

    items, dropped = [], 0
    for raw in (data.get("wishes") or [])[:8] if isinstance(data, dict) else []:
        try:
            wish = Wish.model_validate(raw)
        except ValueError:
            dropped += 1
            continue
        quote = _norm(wish.quote)
        if wish.requirement not in REQUIREMENTS or wish.who not in texts or not quote \
                or quote not in _norm(texts[wish.who]):
            dropped += 1  # not this person's words: never act on an invented wish
            continue
        if not any(w.requirement == wish.requirement and w.who == wish.who for w in items):
            items.append(wish)
    if dropped:
        log.warning("wishes: dropped %d items with an unknown key or a quote not in the text", dropped)
    return Wishes(items=items, source=source, note=f"dropped {dropped}" if dropped else None)


# --- Keyword baseline (for the ablation) ---

KEYWORDS = {
    "outdoor_seating": ("outside", "outdoor", "patio", "terrace", "sidewalk seating"),
    "not_a_chain": ("chain", "independent", "starbucks", "local spot"),
    "wifi": ("wifi", "wi-fi", "internet"),
    "wheelchair_access": ("wheelchair", "step-free", "accessible"),
    "vegan_options": ("vegan",),
    "vegetarian_options": ("vegetarian",),
    "indoor_seating": ("inside", "indoor"),
    "green_meetup": ("park", "green"),
    "viewpoint": ("view",),
}


def keyword_wishes(a_text: str, b_text: str) -> Wishes:
    """A plain keyword matcher: what you get without a language model."""
    items = []
    for who, text in (("A", a_text), ("B", b_text)):
        low = text.lower()
        for key, words in KEYWORDS.items():
            hit = next((w for w in words if re.search(rf"\b{re.escape(w)}\b", low)), None)
            if hit:
                items.append(Wish(requirement=key, who=who, quote=hit))
    return Wishes(items=items, source="keywords")
