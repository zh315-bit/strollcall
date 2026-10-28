"""Invite card: a short invitation (Muse Spark) and an illustration (Muse Image).

Both have deterministic fallbacks, and every result says where it came from
(meta / mock / default) so the page can label demo data.
"""

import logging
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import ProviderError
from app.models.schemas import WalkIntent
from app.providers import meta_or_mock
from app.services.grounding import preference_text, unsupported

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 180

TEXT_PROMPT = """Write the invitation person A sends to a friend for a short walk together, for StrollCall.

Rules:
- One or two warm, casual sentences, at most 160 characters, in English.
- Use only the walk length and preferences given. No place names, addresses, times of day or prices.
- Do not claim anything about safety, crowds, noise or weather.
- No hashtags, no emoji.
Return only JSON matching the schema."""
TEXT_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


def template_text(intent: WalkIntent) -> str:
    text = f"Up for a {intent.duration_min}-minute walk together?"
    if intent.endpoint_type:
        text += f" We'd end at a {intent.endpoint_type.replace('_', ' ')}."
    return text


def invite_text(intent: WalkIntent, a_text: str = "") -> tuple[str, str]:
    """(text, source). The model only words what A asked for; anything else -> template."""
    import json

    user = json.dumps({"walk": intent.model_dump(), "A_wrote": a_text[:300]})
    try:
        data, source = meta_or_mock(lambda m: m.structured_json(TEXT_PROMPT, user, TEXT_SCHEMA, name="invite_text"))
        text = str(data.get("text", "")).strip()
    except ProviderError as e:
        log.warning("invite text fell back to template: %s", e.code)
        return template_text(intent), "default"
    if not text or len(text) > MAX_TEXT_CHARS:
        return template_text(intent), "default"
    problems = unsupported(text, set(), preference_text(intent) + " " + a_text)
    if problems:
        log.warning("invite text discarded (%s); using the template", "; ".join(problems))
        return template_text(intent), "default"
    return text, source


def image_prompt(intent: WalkIntent) -> str:
    """Deterministic: built from A's preferences only, never from places or locations."""
    scene = "a leafy park path" if {"green", "shady"} & set(intent.vibes) or intent.endpoint_type == "park" \
        else "a quiet tree-lined New York side street" if "quiet" in intent.vibes \
        else "a lively New York street with small shops"
    ending = {
        "cafe": "a cozy cafe with two coffee cups", "bakery": "a small bakery window with pastries",
        "bookstore": "a little bookstore front", "ice_cream": "an ice cream window",
        "park": "an open lawn with trees", "landmark": "a classic city monument",
    }.get(intent.endpoint_type or "", "a friendly corner cafe")
    return (f"Warm flat illustration of two friends walking toward each other on {scene}, "
            f"about to continue together toward {ending}. Soft autumn light, gentle colors, "
            "simple shapes. No text, no letters, no logos, no recognizable real people.")


def card_path(token: str) -> Path | None:
    for ext in ("webp", "png", "jpg"):
        p = get_settings().cards_dir / f"{token}.{ext}"
        if p.exists():
            return p
    return None


def make_card_image(token: str, intent: WalkIntent) -> str:
    """Generate and store the card image; returns its source (meta / mock / default)."""
    try:
        data, source = meta_or_mock(lambda m: m.generate_image(image_prompt(intent)))
    except ProviderError as e:
        log.warning("invite image unavailable (%s); card stays text-only", e.code)
        return "default"
    ext = "webp" if data[:4] == b"RIFF" else "png" if data[:4] == b"\x89PNG" else "jpg"
    cards = get_settings().cards_dir
    cards.mkdir(parents=True, exist_ok=True)
    (cards / f"{token}.{ext}").write_bytes(data)
    return source
