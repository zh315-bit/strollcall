"""Free text -> WalkIntent, and A + B -> JointPreference, with Muse Spark.

The model only extracts and reconciles; Pydantic and deterministic checks decide.
"""

import json
import logging

from pydantic import BaseModel, ValidationError

from app.core.errors import ProviderError
from app.models.schemas import JointPreference, WalkIntent
from app.providers import meta_or_mock
from app.providers.overpass import DESTINATION_TYPES

log = logging.getLogger(__name__)

DEFAULT_DURATION_MIN = 25
ENDPOINT_TYPES = list(DESTINATION_TYPES)
INTENT_FIELDS = ["duration_min", "vibes", "endpoint_type", "avoid", "hard_constraints"]

SYSTEM_PROMPT = f"""You turn one person's description of a walk into JSON for StrollCall, an app that plans a short walk for two friends.

Rules:
- Extract only what the person said. Never add preferences they did not express; leave a list empty when nothing was said.
- duration_min: total walking minutes for the outing, 15 to 60. If no duration was given, use {DEFAULT_DURATION_MIN}. If the given value is outside 15-60, use the nearest bound.
- duration_strict: true only if the person signals the time is a hard limit ("only have", "must", "at most", "no more than", "have to be back by"). A plain duration ("25 minutes", "about half an hour") is false.
- vibes: short lowercase phrases for the feel they asked for, such as "quiet", "green", "lively", "scenic".
- endpoint_type: where the walk should end, one of {", ".join(ENDPOINT_TYPES)}; null if they did not say. "coffee" means cafe, "books" means bookstore, "pastries" means bakery, "ice cream" means ice_cream.
- avoid: short lowercase phrases for what they want to avoid.
- hard_constraints: only explicit must-haves, such as "must be open now" or "step-free route".
- Never invent opening hours, safety, accessibility or crowd levels.
- inferred_fields: list every field whose value you chose by default or by interpretation rather than from the person's own words (for example duration_min when no duration was given). Fields taken directly from what they said are stated and are not listed.
Return only JSON matching the schema."""

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "duration_min": {"type": "integer", "minimum": 15, "maximum": 60},
        "duration_strict": {"type": "boolean"},
        "vibes": {"type": "array", "items": {"type": "string"}},
        "endpoint_type": {"type": ["string", "null"], "enum": ENDPOINT_TYPES + [None]},
        "avoid": {"type": "array", "items": {"type": "string"}},
        "hard_constraints": {"type": "array", "items": {"type": "string"}},
        "inferred_fields": {"type": "array", "items": {"type": "string", "enum": INTENT_FIELDS}},
    },
    "required": INTENT_FIELDS + ["duration_strict", "inferred_fields"],
    "additionalProperties": False,
}


class ParsedIntent(BaseModel):
    intent: WalkIntent
    inferred_fields: list[str] = []  # fields not stated by the user, shown differently in the UI
    source: str  # meta (live) / mock (USE_MOCKS or budget cap) / default (provider failed)
    note: str | None = None


def default_intent(reason: str) -> ParsedIntent:
    return ParsedIntent(
        intent=WalkIntent(duration_min=DEFAULT_DURATION_MIN),
        inferred_fields=list(INTENT_FIELDS),
        source="default",
        note=reason,
    )


def _clean(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        item = item.strip().lower()
        if item and item not in seen:
            seen.append(item)
    return seen


def parse_intent(text: str) -> ParsedIntent:
    text = text.strip()
    if not text:
        return default_intent("empty text")

    user = f"Walk description:\n{text}"
    try:
        data, source = meta_or_mock(
            lambda meta: meta.structured_json(SYSTEM_PROMPT, user, INTENT_SCHEMA, name="walk_intent")
        )
    except ProviderError as e:
        log.warning("intent parse fell back to default: %s (%s)", e.code, e.message)
        return default_intent(e.code)

    try:
        intent = WalkIntent.model_validate(data)
    except ValidationError as e:
        fields = ",".join(str(err["loc"][0]) for err in e.errors() if err["loc"])
        log.warning("intent parse fell back to default: model JSON failed validation on %s", fields)
        return default_intent("invalid_model_output")

    intent.vibes = _clean(intent.vibes)
    intent.avoid = _clean(intent.avoid)
    intent.hard_constraints = _clean(intent.hard_constraints)
    inferred = [f for f in data.get("inferred_fields", []) if f in INTENT_FIELDS]
    return ParsedIntent(intent=intent, inferred_fields=inferred, source=source)


# --- Two-person negotiation (DEV_DOC section 5, P0) ---

NEGOTIATION_PROMPT = """You reconcile two friends' walk preferences for StrollCall. Person A invited person B.

Rules:
- Use only the preferences given in the JSON. Never invent new ones.
- shared_vibes: vibes both people asked for, copied exactly from both lists. Empty if none.
- a_priorities / b_priorities: what matters to each person that the other did not ask for, as short phrases taken from their own preferences.
- compromises: 0-3 short sentences on how a conflict between the two inputs is weighed, e.g. "A's cafe and B's park are both acceptable endings." Only mention real conflicts.
- Describe preferences, not the route: never promise stops, places on the way, quiet or busy stretches, or anything else the planner has not checked.
- tradeoff: one sentence for both people summarising how their preferences are balanced. No numbers unless they appear in the input.
- Hard constraints and walk length are decided by the planner, not by you; do not change them.
Return only JSON matching the schema."""

NEGOTIATION_SCHEMA = {
    "type": "object",
    "properties": {
        "shared_vibes": {"type": "array", "items": {"type": "string"}},
        "a_priorities": {"type": "array", "items": {"type": "string"}},
        "b_priorities": {"type": "array", "items": {"type": "string"}},
        "compromises": {"type": "array", "items": {"type": "string"}},
        "tradeoff": {"type": "string"},
    },
    "required": ["shared_vibes", "a_priorities", "b_priorities", "compromises", "tradeoff"],
    "additionalProperties": False,
}
MAX_ITEMS, MAX_ITEM_CHARS, MAX_TRADEOFF_CHARS = 5, 120, 300


class Negotiation(BaseModel):
    joint: JointPreference
    tradeoff: str
    source: str  # meta / mock / default
    note: str | None = None


def _wants(intent: WalkIntent) -> list[str]:
    items = list(intent.vibes)
    if intent.endpoint_type:
        items.append(f"ends at a {intent.endpoint_type.replace('_', ' ')}")
    items += [f"avoid {a}" for a in intent.avoid]
    return items


def default_negotiation(a: WalkIntent, b: WalkIntent, reason: str) -> Negotiation:
    """Deterministic merge, used when Muse Spark is unavailable or its answer is rejected."""
    a_wants, b_wants = _wants(a), _wants(b)
    shared = [v for v in a.vibes if v in b.vibes]
    compromises = []
    if a.endpoint_type and b.endpoint_type and a.endpoint_type != b.endpoint_type:
        compromises.append(f"A asked for a {a.endpoint_type} and B for a {b.endpoint_type}; either can end the walk.")
    if a.duration_min != b.duration_min:
        compromises.append("The walk uses the shorter of the two time budgets.")
    joint = JointPreference(
        shared_vibes=shared,
        a_priorities=[w for w in a_wants if w not in shared and w not in b_wants],
        b_priorities=[w for w in b_wants if w not in shared and w not in a_wants],
        compromises=compromises,
    )
    tradeoff = "Both preferences are kept where they agree; differences are noted above."
    return Negotiation(joint=joint, tradeoff=tradeoff, source="default", note=reason)


def _short_list(items: list[str]) -> list[str]:
    return [i.strip()[:MAX_ITEM_CHARS] for i in items if i.strip()][:MAX_ITEMS]


def negotiate(a: WalkIntent, b: WalkIntent) -> Negotiation:
    """Muse Spark reconciles both preferences into a JointPreference. It never touches
    duration or hard constraints; the planner applies those from both intents."""
    user = json.dumps({"A": a.model_dump(), "B": b.model_dump()})
    try:
        data, source = meta_or_mock(
            lambda meta: meta.structured_json(NEGOTIATION_PROMPT, user, NEGOTIATION_SCHEMA,
                                              name="joint_preference")
        )
    except ProviderError as e:
        log.warning("negotiation fell back to default: %s (%s)", e.code, e.message)
        return default_negotiation(a, b, e.code)

    try:
        joint = JointPreference.model_validate(data)
        tradeoff = str(data["tradeoff"]).strip()
    except (ValidationError, KeyError):
        log.warning("negotiation fell back to default: model JSON failed validation")
        return default_negotiation(a, b, "invalid_model_output")

    # Shared vibes must be vibes both people actually gave.
    allowed = set(a.vibes) & set(b.vibes)
    invented = [v for v in joint.shared_vibes if v.strip().lower() not in allowed]
    if invented:
        log.warning("negotiation: dropped %d shared vibes not given by both people", len(invented))
    joint = JointPreference(
        shared_vibes=[v.strip().lower() for v in joint.shared_vibes if v.strip().lower() in allowed],
        a_priorities=_short_list(joint.a_priorities),
        b_priorities=_short_list(joint.b_priorities),
        compromises=_short_list(joint.compromises)[:3],
    )
    if not tradeoff or len(tradeoff) > MAX_TRADEOFF_CHARS:
        return default_negotiation(a, b, "invalid_model_output")
    # The model saw only the two intents: any place feature it mentions must come from them.
    from app.services.grounding import preference_text, unsupported

    problems = [p for text in joint.compromises + [tradeoff]
                for p in unsupported(text, set(), preference_text(a, b))]
    if problems:
        log.warning("negotiation text discarded (%s); using the deterministic one", "; ".join(problems))
        return default_negotiation(a, b, "unsupported_feature")
    return Negotiation(joint=joint, tradeoff=tradeoff, source=source)


def combined_intent(a: WalkIntent, b: WalkIntent) -> WalkIntent:
    """Deterministic planner input for two people: hard limits from both, never relaxed."""
    if a.endpoint_type and b.endpoint_type and a.endpoint_type != b.endpoint_type:
        endpoint = None  # conflict: any type; the ranking step weighs it
    else:
        endpoint = a.endpoint_type or b.endpoint_type
    merge = lambda x, y: list(dict.fromkeys(x + y))  # noqa: E731
    shorter = a if a.duration_min <= b.duration_min else b
    strict = shorter.duration_strict or (a.duration_min == b.duration_min and (a.duration_strict or b.duration_strict))
    return WalkIntent(
        duration_min=min(a.duration_min, b.duration_min),
        duration_strict=strict,
        vibes=merge(a.vibes, b.vibes),
        endpoint_type=endpoint,
        avoid=merge(a.avoid, b.avoid),
        hard_constraints=merge(a.hard_constraints, b.hard_constraints),
    )
