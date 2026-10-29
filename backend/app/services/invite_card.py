"""Invite card: a short invitation (Muse Spark) and an illustration (Muse Image, pre-generated).

Both have deterministic fallbacks, and every result says where it came from
(meta / mock / default) so the page can label demo data.
"""

import logging

from app.core.config import ROOT_DIR
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
    problems = unsupported(text, set(), preference_text(intent) + " " + a_text, speaker_is_the_person=True)
    if problems:
        log.warning("invite text discarded (%s); using the template", "; ".join(problems))
        return template_text(intent), "default"
    return text, source


# --- Illustration: one of 24 pre-generated Muse Image pictures, picked by theme ---
# Generated once with scripts/make_illustrations.py (model and exact prompt per file in
# frontend/illustrations/manifest.json). Picking by theme needs no Meta call per invite, works the
# same on every host, and survives the free plan's ephemeral disk.

SCENES = {
    "park": "a leafy park path",
    "quiet": "a quiet tree-lined New York side street",
    "historic": "a historic New York brownstone street",
    "lively": "a lively New York street with small shops",
}
ENDINGS = {  # the six endpoint types; "anywhere" uses the cafe picture, as before
    "cafe": "a friendly corner cafe with two coffee cups", "bakery": "a small bakery window with pastries",
    "bookstore": "a little bookstore front", "ice_cream": "an ice cream window",
    "park": "an open lawn with trees", "landmark": "a classic city monument",
}
ILLUSTRATIONS_DIR = ROOT_DIR / "frontend" / "illustrations"


def theme_for(intent: WalkIntent) -> tuple[str, str]:
    """(scene, ending) from A's preferences only, never from places or locations."""
    vibes = set(intent.vibes)
    scene = ("park" if {"green", "shady"} & vibes or intent.endpoint_type == "park"
             else "quiet" if "quiet" in vibes
             else "historic" if {"historic", "scenic"} & vibes or intent.endpoint_type == "landmark"
             else "lively")
    ending = intent.endpoint_type if intent.endpoint_type in ENDINGS else "cafe"
    return scene, ending


def theme_prompt(scene: str, ending: str) -> str:
    return (f"Warm flat illustration of exactly two friends, no other people, walking toward each other on "
            f"{SCENES[scene]}, about to continue together toward {ENDINGS[ending]}. Soft autumn light, gentle "
            "colors, simple shapes. No text, no letters, no logos, no recognizable real people.")


def image_prompt(intent: WalkIntent) -> str:
    return theme_prompt(*theme_for(intent))


def illustration_file(scene: str, ending: str) -> str:
    return f"{scene}-{ending}.jpg"


def pick_illustration(intent: WalkIntent) -> tuple[str | None, str]:
    """(URL path, source) of the pre-generated picture for this intent's theme.
    source is "meta" (made by Muse Image) or "default" when it has not been generated."""
    name = illustration_file(*theme_for(intent))
    if (ILLUSTRATIONS_DIR / name).exists():
        return f"/static/illustrations/{name}", "meta"
    return None, "default"
