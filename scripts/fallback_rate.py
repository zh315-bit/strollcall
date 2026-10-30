"""How often Muse Spark's negotiation and ranking are rejected by the honesty checks, on the
pre-registered wish and conflict cases (fixtures/wish_cases.json, fixtures/conflict_cases.json).

    python scripts/fallback_rate.py --label before --runs 2
    python scripts/fallback_rate.py --label after --runs 2
    python scripts/fallback_rate.py --label repro --live-pair --runs 5   # the 2026-10-30 live-flow inputs

Each case runs the Meta path of an accepted invite: negotiation, wishes, the local planner, ranking. A
fallback is counted only when Meta answered and the answer was rejected (or failed to parse); calls that
did not reach Meta (unavailable, budget) are counted apart. Every rejected text is written to the report
so each one can be classified as a checker false positive or a real overclaim.
Writes benchmarks/YYYY-MM-DD-fallback-<label>.md. Bounded by the daily spend guard.
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ["USE_MOCKS"] = "false"

from _common import ROOT, load_conflict_cases, load_wish_cases  # noqa: E402

from app.core.budget import SpendGuard  # noqa: E402
from app.core.config import get_settings, reasoning_override  # noqa: E402
from app.models.schemas import WalkIntent  # noqa: E402
from app.providers.local_routing import LocalRouting, load_graph  # noqa: E402
from app.providers.snapshot_places import SnapshotPlaces, load_snapshot  # noqa: E402
from app.services.explain import rank_candidates  # noqa: E402
from app.services.intent import negotiate  # noqa: E402
from app.services.planner import plan_for_two  # noqa: E402
from app.services.wishes import interpret_wishes  # noqa: E402

NYC = ZoneInfo("America/New_York")
NOT_REACHED = {"model_unavailable", "budget_exceeded", "rate_limited", "timeout", "meta_unavailable", "nothing_to_rank"}


class Rejections(logging.Handler):
    """Collects the checkers' warnings (they carry the rejected text)."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record):
        msg = record.getMessage()
        if any(k in msg for k in ("discarded", "rejected", "not in the facts", "fell back", "failed validation")):
            self.messages.append(f"{record.name.split('.')[-1]}: {msg}")


def live_pair_case() -> dict:
    """The inputs of the live runs on 2026-10-30 (public places), for reproducing those rejections."""
    return {"id": "live", "a": (40.7359, -73.9906), "b": (40.7308, -73.9973),
            "intent": None, "b_intent": None,  # parsed by Muse Spark from the texts, as in the app
            "a_text": "about 25 minutes, quiet streets, coffee at the end",
            "b_text": "I'd like to pass a park, not too long",
            "depart_at": datetime.now(NYC).replace(hour=15, minute=0, second=0, microsecond=0)}


def outcome(source: str, note: str | None) -> str:
    if source == "meta":
        return "meta"
    if note in NOT_REACHED or (note or "").startswith("model"):
        return f"not reached ({note})"
    return f"rejected ({note})"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--live-pair", action="store_true", help="only the 2026-10-30 live-flow inputs")
    args = parser.parse_args()
    s = get_settings()
    reasoning_override.set(s.accept_reasoning_effort)  # as in the app after B accepts
    places, graph = SnapshotPlaces(load_snapshot(s.places_snapshot_path)), load_graph(s.graph_path)
    handler = Rejections()
    logging.getLogger("app").addHandler(handler)
    guard = SpendGuard()
    before = guard.today_total()

    cases = [live_pair_case()] if args.live_pair else [
        c for c in load_wish_cases() + load_conflict_cases() if c["b_intent"] is not None and c["a_text"]]
    rows = []
    for run in range(1, args.runs + 1):
        for case in cases:
            handler.messages.clear()
            a, b = case["intent"], case["b_intent"]
            if a is None:
                from app.services.intent import parse_intent

                a, b = parse_intent(case["a_text"]).intent, parse_intent(case["b_text"]).intent
            neg = negotiate(a, b)
            wishes = interpret_wishes(case["a_text"], case["b_text"])
            plan = plan_for_two(case["a"], case["b"], a, b, neg.joint, places, LocalRouting(graph),
                                case["depart_at"], wishes=wishes)
            ranking = rank_candidates(plan, a, b, neg.joint, wishes) if plan.status == "proposed" else None
            row = {"run": run, "id": case["id"], "neg": outcome(neg.source, neg.note),
                   "rank": outcome(ranking.source, ranking.note) if ranking else f"no plan ({plan.status})",
                   "n": len(plan.candidates), "why": list(handler.messages)}
            rows.append(row)
            print(f"run {run} {case['id']}: negotiation {row['neg']}, ranking {row['rank']}", flush=True)

    def rate(key):
        judged = [r[key] for r in rows if r[key] == "meta" or r[key].startswith("rejected")]
        bad = sum(x.startswith("rejected") for x in judged)
        return bad, len(judged)

    nb, nn = rate("neg")
    rb, rn = rate("rank")
    spend = guard.today_total() - before
    lines = [
        f"# Fallback rate of Muse Spark's negotiation and ranking: {args.label}",
        "",
        f"Run {datetime.now(NYC):%Y-%m-%d %H:%M} ET, `scripts/fallback_rate.py --label {args.label} --runs {args.runs}"
        + (" --live-pair" if args.live_pair else "") + "`, model "
        f"{s.model_id} at `{s.accept_reasoning_effort}` reasoning effort (as after an invite is accepted), local "
        "walking graph and place snapshot, up to six options per plan. "
        + ("Inputs: the 2026-10-30 live-flow pair (Union Square Park ↔ Washington Square Arch)."
           if args.live_pair else
           "Cases: every pre-registered wish case (fixtures/wish_cases.json) and conflict case "
           "(fixtures/conflict_cases.json) with B's preference and free text; written before any prompt change."),
        "",
        "A fallback counts only when Meta answered and the honesty checks (or the schema) rejected the answer.",
        "",
        f"- **Negotiation rejected: {nb} of {nn}** ({(100 * nb / nn) if nn else 0:.0f}%)",
        f"- **Ranking rejected: {rb} of {rn}** ({(100 * rb / rn) if rn else 0:.0f}%)",
        f"- Meta spend for this run: ${spend:.3f}",
        "",
        "| Run | Case | Options | Negotiation | Ranking |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [f"| {r['run']} | {r['id']} | {r['n']} | {r['neg']} | {r['rank']} |" for r in rows]
    lines += ["", "## Rejected texts", ""]
    for r in rows:
        for m in r["why"]:
            lines.append(f"- run {r['run']} {r['id']}: {m}")
    if not any(r["why"] for r in rows):
        lines.append("None.")
    out = ROOT / "benchmarks" / f"{datetime.now(NYC):%Y-%m-%d}-fallback-{args.label}.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"negotiation rejected {nb}/{nn}, ranking rejected {rb}/{rn}, spend ${spend:.3f}; wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
