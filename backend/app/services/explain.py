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

MAX_REASON_CHARS = 240
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
LABEL_RE = re.compile(r"\bc\d\b")  # candidate labels are not facts

RANKING_PROMPT = """You rank walk plans for two friends, A and B, for StrollCall.

You get their preferences, how they were reconciled, and 2-3 candidate plans that a route
planner has already checked: every plan is walkable, within the time budget and fair.

Rules:
- Rank only the candidates given, by id. Return each id exactly once.
- For each, give one short reason (max 30 words) that refers to A's and B's preferences.
- Use only the facts given. Do not invent places, opening hours, safety, crowds or noise.
- Any number you write must appear in that candidate's facts.
Return only JSON matching the schema."""


class Ranking(BaseModel):
    candidates: list[MeetupCandidate]  # reordered
    reasons: dict[str, str] = {}  # candidate id -> Meta's reason ({} for deterministic)
    source: str  # meta / mock / default
    note: str | None = None


def _facts(result: PlanResult) -> tuple[dict[str, MeetupCandidate], list[dict]]:
    labelled, facts = {}, []
    for i, c in enumerate(result.candidates, start=1):
        label = f"c{i}"
        labelled[label] = c
        meet, dest = result.places[c.meeting_place_id], result.places[c.endpoint_place_id]
        facts.append({
            "id": label,
            "meet_at": {"name": meet.name, "kind": meet.category},
            "destination": {
                "name": dest.name,
                "kind": dest.category,
                "opening_hours": "listed in OpenStreetMap" if dest.opening_hours else "unknown",
            },
            "a_walk_min": round(c.a_leg.duration_min),
            "b_walk_min": round(c.b_leg.duration_min),
            "arrival_gap_min": round(c.arrival_gap_min, 1),
            "walk_together_min": round(c.shared_leg.duration_min),
            "total_min": round(c.total_elapsed_min),
        })
    return labelled, facts


def _allowed_numbers(fact: dict, a: WalkIntent, b: WalkIntent) -> set[float]:
    values = [v for k, v in fact.items() if k.endswith("_min")] + [a.duration_min, b.duration_min]
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
    result: PlanResult, a: WalkIntent, b: WalkIntent, joint: JointPreference
) -> Ranking:
    if result.status != "proposed" or len(result.candidates) < 2:
        return deterministic(result, "nothing_to_rank")

    labelled, facts = _facts(result)
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

    problem = _check(data, labelled, {f["id"]: f for f in facts}, a, b) or _grounded(data, labelled, result, a, b)
    if problem:
        log.warning("ranking fell back to deterministic order: %s", problem)
        return deterministic(result, problem)

    order = [item["id"] for item in data["ranking"]]
    return Ranking(
        candidates=[labelled[label] for label in order],
        reasons={labelled[item["id"]].id: item["reason"].strip() for item in data["ranking"]},
        source=source,
    )


def _check(data: dict, labelled: dict, facts: dict, a: WalkIntent, b: WalkIntent) -> str | None:
    """Reason for rejecting the model's ranking, or None if it is usable."""
    items = data.get("ranking") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return "invalid_model_output"
    ids = [i.get("id") for i in items if isinstance(i, dict)]
    if sorted(ids) != sorted(labelled):
        return "ranking_ids_mismatch"
    for item in items:
        reason = str(item.get("reason", "")).strip()
        if not reason or len(reason) > MAX_REASON_CHARS:
            return "reason_length"
        allowed = _allowed_numbers(facts[item["id"]], a, b)
        for n in NUMBER_RE.findall(LABEL_RE.sub("", reason)):
            if float(n) not in allowed:
                return "invented_number"
    return None


def _grounded(data: dict, labelled: dict, result: PlanResult, a: WalkIntent, b: WalkIntent) -> str | None:
    """Every place feature in a reason must be in that candidate's data or a stated preference."""
    from app.services.grounding import place_evidence, preference_text, unsupported

    prefs = preference_text(a, b)
    for item in data["ranking"]:
        c = labelled[item["id"]]
        evidence = place_evidence([result.places[c.meeting_place_id], result.places[c.endpoint_place_id]])
        problems = unsupported(item["reason"], evidence, prefs)
        if problems:
            log.warning("ranking reason for %s rejected: %s", item["id"], "; ".join(problems))
            return "unsupported_feature"
    return None
