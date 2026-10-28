"""Free text -> WalkIntent with Muse Spark. The model only extracts; Pydantic decides."""

import logging

from pydantic import BaseModel, ValidationError

from app.core.errors import ProviderError
from app.models.schemas import WalkIntent
from app.providers import meta_or_mock

log = logging.getLogger(__name__)

DEFAULT_DURATION_MIN = 25
ENDPOINT_TYPES = ["cafe", "park", "bookstore", "landmark"]
INTENT_FIELDS = ["duration_min", "vibes", "endpoint_type", "avoid", "hard_constraints"]

SYSTEM_PROMPT = f"""You turn one person's description of a walk into JSON for StrollCall, an app that plans a short walk for two friends.

Rules:
- Extract only what the person said. Never add preferences they did not express; leave a list empty when nothing was said.
- duration_min: total walking minutes for the outing, 15 to 60. If no duration was given, use {DEFAULT_DURATION_MIN}. If the given value is outside 15-60, use the nearest bound.
- vibes: short lowercase phrases for the feel they asked for, such as "quiet", "green", "lively", "scenic".
- endpoint_type: where the walk should end, one of {", ".join(ENDPOINT_TYPES)}; null if they did not say. "coffee" means cafe, "books" means bookstore.
- avoid: short lowercase phrases for what they want to avoid.
- hard_constraints: only explicit must-haves, such as "must be open now" or "step-free route".
- Never invent opening hours, safety, accessibility or crowd levels.
- inferred_fields: list every field whose value you chose by default or by interpretation rather than from the person's own words (for example duration_min when no duration was given). Fields taken directly from what they said are stated and are not listed.
Return only JSON matching the schema."""

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "duration_min": {"type": "integer", "minimum": 15, "maximum": 60},
        "vibes": {"type": "array", "items": {"type": "string"}},
        "endpoint_type": {"type": ["string", "null"], "enum": ENDPOINT_TYPES + [None]},
        "avoid": {"type": "array", "items": {"type": "string"}},
        "hard_constraints": {"type": "array", "items": {"type": "string"}},
        "inferred_fields": {"type": "array", "items": {"type": "string", "enum": INTENT_FIELDS}},
    },
    "required": INTENT_FIELDS + ["inferred_fields"],
    "additionalProperties": False,
}


class ParsedIntent(BaseModel):
    intent: WalkIntent
    inferred_fields: list[str] = []  # fields not stated by the user, shown differently in the UI
    source: str  # meta / mock / default
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
