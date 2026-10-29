"""Check that model-written explanations only mention place features we actually have.

A feature (park, cafe, waterfront, ...) is allowed when the data given to the model
supports it: the candidates' categories, OSM tags and names, or a preference A or B
stated. Attributes our data can never confirm (quiet, safe, crowded, shaded, ...) are
allowed only when they clearly describe someone's preference ("B's quiet wish"). Claims
about what lies along the route are never allowed: the model gets no route details.
"""

import re

from app.models.schemas import Place, WalkIntent

# feature key -> pattern (word-ish boundaries, case-insensitive)
FEATURES = {
    "park": r"parks?|green ?space|garden|greenery|lawn",
    "cafe": r"caf[eé]s?|coffee|espresso",
    "bakery": r"bakery|bakeries|pastr(?:y|ies)|bread",
    "ice_cream": r"ice ?cream|gelato",
    "bookstore": r"book ?stores?|bookshops?|books",
    "plaza": r"plazas?|squares?",
    "landmark": r"landmarks?|memorials?|monuments?|statues?|museums?|historic",
    "subway": r"subway|station",
    "gate": r"gates?",
    "water": r"waterfront|river|pier|harbou?r|water",
    "viewpoint": r"views?|viewpoints?|scenic|skyline",
    "playground": r"playgrounds?",
    "fountain": r"fountains?",
    "seating": r"benches?|outdoor seating|seating outside|sit outside|outdoors?|patio|terrace",
    "vegan": r"vegan|vegetarian|plant[- ]based",
    "wifi": r"wi-?fi|internet|laptop",
    "chain": r"chains?|independent|branded",
    "access": r"step[- ]free|accessible|wheelchair",
    "trees": r"trees?|leafy",
}
# Things no data source here can confirm; only allowed as someone's stated preference.
UNVERIFIABLE = {
    "quiet": r"quiet(?:er)?|calm|peaceful|tranquil",
    "busy": r"busy|crowd(?:s|ed)?|lively|bustling|noisy|traffic",
    "safety": r"safe(?:ty|r)?|unsafe|well[- ]lit|lit",
    "shade": r"shad(?:e|y|ed)",
}
ROUTE_CLAIMS = r"on the way|along the way|en route|passes|passing|stretch(?:es)?|through (?:a|the) park|detour via|stop at|a .{0,20} stop\b"
PREFERENCE_CUES = r"(?:\b[AB]'s\b|\bfor [AB]\b|\b[AB] (?:wants|asked|prefers|likes)\b|\bwish|\bwant|\bprefer|\bpreference|\basked|\brequest|\bavoid)"

_FEATURE_RE = {k: re.compile(rf"\b(?:{p})\b", re.I) for k, p in FEATURES.items()}
_UNVERIFIABLE_RE = {k: re.compile(rf"\b(?:{p})\b", re.I) for k, p in UNVERIFIABLE.items()}
_ROUTE_RE = re.compile(rf"\b(?:{ROUTE_CLAIMS})", re.I)
_CUE_RE = re.compile(PREFERENCE_CUES, re.I)

CATEGORY_FEATURES = {
    "park": {"park"}, "park_gate": {"park", "gate"}, "cafe": {"cafe"}, "bakery": {"bakery"},
    "ice_cream": {"ice_cream"}, "bookstore": {"bookstore"}, "plaza": {"plaza"},
    "landmark": {"landmark"}, "subway_entrance": {"subway"},
}


def features_in(text: str) -> set[str]:
    return {k for k, r in _FEATURE_RE.items() if r.search(text)}


def place_evidence(places: list[Place]) -> set[str]:
    found: set[str] = set()
    for p in places:
        found |= CATEGORY_FEATURES.get(p.category, set())
        found |= features_in(p.name)
        if p.tags.get("tourism") == "viewpoint":
            found.add("viewpoint")
        if p.tags.get("outdoor_seating") not in (None, "no"):
            found.add("seating")
        if p.tags.get("diet:vegan") in ("yes", "only") or p.tags.get("diet:vegetarian") in ("yes", "only"):
            found.add("vegan")
        if p.tags.get("internet_access") not in (None, "no"):
            found.add("wifi")
        if p.tags.get("wheelchair") in ("yes", "designated"):
            found.add("access")
        if p.category in ("cafe", "bakery", "ice_cream", "bookstore"):
            found.add("chain")  # chain status is known from the brand tag either way
        if p.opening_hours:
            found.add("hours")
    return found


def preference_text(*intents: WalkIntent) -> str:
    parts = []
    for i in intents:
        parts += i.vibes + i.avoid + i.hard_constraints + ([i.endpoint_type.replace("_", " ")] if i.endpoint_type else [])
    return " ".join(parts)


def _is_preference_mention(text: str, start: int, end: int) -> bool:
    """A cue such as "B's", "for A", "wish", "prefers" within a few words of the term."""
    window = text[max(0, start - 30): end + 30]
    return bool(_CUE_RE.search(window))


def unsupported(text: str, evidence: set[str], preferences: str, speaker_is_the_person: bool = False) -> list[str]:
    """Feature claims in `text` the data does not support; [] when the text is grounded.

    speaker_is_the_person: the text is written as the person (an invite card), so a word they
    used themselves ("quiet") is their wish, not a claim about a place.
    """
    problems = []
    if m := _ROUTE_RE.search(text):
        problems.append(f"route claim: '{m.group(0)}'")
    stated = features_in(preferences)
    for key, r in _FEATURE_RE.items():
        if r.search(text) and key not in evidence and key not in stated:
            problems.append(f"feature not in data: {key}")
    for key, r in _UNVERIFIABLE_RE.items():
        for m in r.finditer(text):
            stated = re.search(r.pattern, preferences, re.I)
            if not (stated and (speaker_is_the_person or _is_preference_mention(text, m.start(), m.end()))):
                problems.append(f"unverifiable claim: '{m.group(0)}'")
                break
    return problems


# --- Place intros (scripts/make_poi_intros.py): a rewrite must not say more than its source ---

INTRO_MAX_CHARS = 300
EVALUATIVE = r"famous|iconic|beautiful|stunning|popular|beloved|must[- ]see|best|oldest|largest|tallest|first|only"
_EVALUATIVE_RE = re.compile(rf"\b(?:{EVALUATIVE})\b", re.I)
_NUMBER_RE = re.compile(r"\d[\d,.]*")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’.-]*")
# A sentence ends at . ! ? before a capital, but not after an initial ("J. Leonard", "U.S.") or a
# common abbreviation ("St. Mark's").
_SENTENCE_END = re.compile(r"(?<![A-Z])(?<!\bSt)(?<!\bMt)(?<!\bDr)(?<!\bJr)(?<!\bSr)(?<!\bMr)(?<!\bNo)(?<!\bft)"
                           r"(?<!\bvs)(?<!\bca)[.!?]\s+(?=[A-Z\"“])")


def sentences(text: str) -> list[str]:
    return [x for x in _SENTENCE_END.split(text.strip()) if x.strip()]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'")).lower()


def intro_problems(intro: str, source: str, name: str) -> list[str]:
    """Reasons to drop a model-written intro; [] when every checkable fact is in the source.

    Checks: at most 2 sentences and INTRO_MAX_CHARS; every number, every capitalised word that
    does not start a sentence, every place feature (park, museum, river, ...), and every
    unverifiable or evaluative word (quiet, safe, famous, oldest, ...) must appear in the source
    text or the place's name; no claims about the route.
    """
    problems = []
    src = _norm(source + " " + name)
    if len(intro) > INTRO_MAX_CHARS:
        problems.append(f"longer than {INTRO_MAX_CHARS} characters")
    if len(sentences(intro)) > 2:
        problems.append("more than 2 sentences")
    for num in _NUMBER_RE.findall(intro):
        if num.rstrip(".,") not in src:
            problems.append(f"number not in source: {num}")
    for sentence in sentences(intro):
        for i, m in enumerate(_WORD_RE.finditer(sentence)):
            w = re.sub(r"'s$", "", m.group(0).rstrip(".").replace("’", "'"))  # Park's -> Park
            if i > 0 and w[0].isupper() and w.lower() not in src:
                problems.append(f"name not in source: {w}")
    source_features = features_in(source + " " + name)
    for key in features_in(intro) - source_features:
        problems.append(f"feature not in source: {key}")
    for key, r in _UNVERIFIABLE_RE.items():
        if r.search(intro) and not r.search(source):
            problems.append(f"unverifiable claim: {key}")
    for m in _EVALUATIVE_RE.finditer(intro):
        if m.group(0).lower() not in src:
            problems.append(f"evaluative word not in source: {m.group(0)}")
    if (m := _ROUTE_RE.search(intro)) and m.group(0).lower() not in src:
        problems.append(f"route claim: {m.group(0)}")
    return problems
