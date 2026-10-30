"""Meta ranking of the planner's top candidates (fallback ladder rung 1).

Muse Spark sees only the candidates the deterministic planner already found feasible,
under short labels (c1, c2, c3), with their measured facts. It may reorder them and
explain why; it cannot add places, change times or override a hard constraint. Every
number in its explanations must be one of the facts it was given, otherwise the whole
ranking is rejected and the deterministic order stands (rung 2).
"""

import json
import logging
import re

from pydantic import BaseModel

from app.core.errors import ProviderError
from app.models.schemas import JointPreference, MeetupCandidate, WalkIntent
from app.providers import meta_or_mock
from app.services.planner import PlanResult

log = logging.getLogger(__name__)

MAX_REASON_CHARS = 280
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
LABEL_RE = re.compile(r"\bc\d\b")  # candidate labels are not facts
ORDINAL_RE = re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.I)  # "5th" in "5th Ave & E 12th St"


def _without_names(text: str, names: list[str]) -> str:
    """The text with the candidates' place names taken out, longest first: a name is a fact,
    not a claim, also when shortened ("the 5th Ave plan" for "5th Ave & E 12th St")."""
    for name in names:
        text = text.replace(name, " ")
    ordinals = {o.lower() for name in names for o in ORDINAL_RE.findall(name)}
    return ORDINAL_RE.sub(lambda m: " " if m.group(0).lower() in ordinals else m.group(0), text)


def _place_names(result: PlanResult) -> list[str]:
    names = {result.places[c.meeting_place_id].name for c in result.candidates}
    names |= {result.places[c.endpoint_place_id].name for c in result.candidates}
    return sorted(names, key=len, reverse=True)

RANKING_PROMPT = """You rank walk plans for two friends, A and B, for StrollCall.

You get their preferences, how they were reconciled, and 2-3 candidate plans that a route
planner has already checked: every plan is walkable, within the time budget and fair.

Rules:
- Rank only the candidates given, by id. Return each id exactly once.
- For each, give one short reason (max 35 words) that compares it with the other options using
  the facts, e.g. "3 min shorter than the Starbucks plan, but Wi-Fi unconfirmed", and says who each
  part is for, using the "suits" facts (e.g. "meet at the park for B, end at the cafe for A").
- Refer to other options by their meeting point or destination name, never by id (c1, c2, c3).
- Use only the facts given. Do not invent places, opening hours, safety, crowds or noise.
- Wishes marked "unknown" are not confirmed: never say they are met.
- Any number you write must appear in that candidate's facts.
Return only JSON matching the schema."""


class Ranking(BaseModel):
    candidates: list[MeetupCandidate]  # reordered
    reasons: dict[str, str] = {}  # candidate id -> Meta's reason ({} for deterministic)
    source: str  # meta / mock / default
    note: str | None = None


def _facts(result: PlanResult, wishes=None, people=None) -> tuple[dict[str, MeetupCandidate], list[dict]]:
    from app.services.planner import served
    from app.services.wishes import REQUIREMENTS, requirement_status

    labelled, facts = {}, []
    for i, c in enumerate(result.candidates, start=1):
        label = f"c{i}"
        labelled[label] = c
        meet, dest = result.places[c.meeting_place_id], result.places[c.endpoint_place_id]
        who = served(meet, dest, people)
        facts.append({
            "id": label,
            "meet_at": {"name": meet.name, "kind": meet.category, "suits": who["meetup"]},
            "destination": {
                "name": dest.name,
                "kind": dest.category,
                "suits": who["destination"],
                "opening_hours": "listed in OpenStreetMap" if dest.opening_hours else "unknown",
            },
            "a_walk_min": round(c.a_leg.duration_min),
            "b_walk_min": round(c.b_leg.duration_min),
            "arrival_gap_min": round(c.arrival_gap_min, 1),
            "walk_together_min": round(c.shared_leg.duration_min),
            "total_min": round(c.total_elapsed_min),
        })
        if wishes is not None and wishes.items:
            status = {True: "yes", False: "no", None: "unknown (not in OpenStreetMap)"}
            facts[-1]["wishes"] = [
                {"who": w.who, "wish": REQUIREMENTS[w.requirement].description,
                 "met": status[requirement_status(w, meet, dest)]}
                for w in wishes.items
            ]
    return labelled, facts


def _allowed_numbers(facts: list[dict], a: WalkIntent, b: WalkIntent) -> set[float]:
    """Every measured number of every candidate, and the differences between candidates."""
    def numbers(f):
        return {k: v for k, v in f.items() if k.endswith("_min")}

    values = [a.duration_min, b.duration_min]
    for f in facts:
        values += numbers(f).values()
    for f in facts:
        for g in facts:
            if f is not g:
                values += [abs(numbers(f)[k] - numbers(g)[k]) for k in numbers(f)]
    allowed = set()
    for v in values:
        allowed |= {float(v), float(round(v)), round(float(v), 1)}
    return allowed


def _schema(labels: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "ranking": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": labels},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["ranking"],
        "additionalProperties": False,
    }


def deterministic(result: PlanResult, reason: str) -> Ranking:
    return Ranking(candidates=list(result.candidates), source="default", note=reason)


def rank_candidates(
    result: PlanResult, a: WalkIntent, b: WalkIntent, joint: JointPreference, wishes=None
) -> Ranking:
    if result.status != "proposed" or len(result.candidates) < 2:
        return deterministic(result, "nothing_to_rank")

    labelled, facts = _facts(result, wishes, {"A": a, "B": b})
    user = json.dumps({
        "A": a.model_dump(), "B": b.model_dump(), "joint_preference": joint.model_dump(),
        "candidates": facts,
    })
    try:
        data, source = meta_or_mock(
            lambda meta: meta.structured_json(RANKING_PROMPT, user, _schema(list(labelled)),
                                              name="candidate_ranking")
        )
    except ProviderError as e:
        log.warning("ranking fell back to deterministic order: %s (%s)", e.code, e.message)
        return deterministic(result, e.code)

    problem = _check(data, labelled, facts, a, b) or _grounded(data, labelled, result, a, b, wishes)
    if problem:
        log.warning("ranking fell back to deterministic order: %s", problem)
        return deterministic(result, problem)

    order = [item["id"] for item in data["ranking"]]
    return Ranking(
        candidates=[labelled[label] for label in order],
        reasons={labelled[item["id"]].id: item["reason"].strip() for item in data["ranking"]},
        source=source,
    )


def _check(data: dict, labelled: dict, facts: list[dict], a: WalkIntent, b: WalkIntent) -> str | None:
    """Reason for rejecting the model's ranking, or None if it is usable."""
    items = data.get("ranking") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return "invalid_model_output"
    ids = [i.get("id") for i in items if isinstance(i, dict)]
    if sorted(ids) != sorted(labelled):
        return "ranking_ids_mismatch"
    allowed = _allowed_numbers(facts, a, b)
    # Digits inside place names ("787 Coffee Co.", "E 13th St") are not claims: remove the names first.
    names = sorted({f[k]["name"] for f in facts for k in ("meet_at", "destination")}, key=len, reverse=True)
    for item in items:
        reason = str(item.get("reason", "")).strip()
        if not reason or len(reason) > MAX_REASON_CHARS:
            return "reason_length"
        if LABEL_RE.search(reason):
            return "internal_label_in_reason"  # users never see c1 / c2 / c3
        for n in NUMBER_RE.findall(_without_names(reason, names)):
            if float(n) not in allowed:
                log.warning("ranking reason has a number not in the facts: %s in %r", n, reason[:160])
                return "invented_number"
    return None


def _grounded(data: dict, labelled: dict, result: PlanResult, a: WalkIntent, b: WalkIntent,
              wishes=None) -> str | None:
    """Every place feature in a reason must be in that candidate's data or a stated preference
    (including the wishes Muse Spark read in their text, e.g. "meet in or at the edge of a park")."""
    from app.services.grounding import place_evidence, preference_text, unsupported
    from app.services.wishes import REQUIREMENTS

    prefs = preference_text(a, b)
    # Reasons compare with the other options by name; "Dominique Ansel Bakery" named as another
    # option is not a bakery claim about this one. Features are checked on the rest of the text.
    names = _place_names(result)
    if wishes is not None:
        prefs += " " + " ".join(REQUIREMENTS[w.requirement].description for w in wishes.items)
    for item in data["ranking"]:
        c = labelled[item["id"]]
        evidence = place_evidence([result.places[c.meeting_place_id], result.places[c.endpoint_place_id]])
        problems = unsupported(_without_names(item["reason"], names), evidence, prefs)
        if problems:
            log.warning("ranking reason for %s rejected: %s", item["id"], "; ".join(problems))
            return "unsupported_feature"
    return None
