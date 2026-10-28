"""Meta ablation: what do Muse Spark's jobs change in the plan, measured against a human reference?

    python scripts/ablation.py                # benchmark conflict cases
    python scripts/ablation.py --wish-cases   # pre-registered wish cases (fixtures/wish_cases.json)
    python scripts/ablation.py --conflict-cases   # pre-registered A-vs-B conflicts (fixtures/conflict_cases.json)

For every benchmark case with a B preference and free text (fixtures/benchmark_cases.json), on the
local engine, three arms with identical hard constraints:
  (a)  structured:  rule-based merge of both WalkIntents; deterministic ranking (rung 2)
  (a') keywords:    (a) + wishes found by a plain keyword matcher in the free text
  (b)  Meta:        Muse Spark negotiation + Muse Spark wishes (quoted, menu-limited) in the fit
                    term and shortlist + Muse Spark ranking of the top 3 (rung 1)
Every arm's top pick is scored against expected_wishes, written by hand before the run.
Writes benchmarks/YYYY-MM-DD-ablation.md with explanations side by side for human review.
"""

import argparse
import os
import statistics
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ["USE_MOCKS"] = "false"

import re  # noqa: E402

from _common import ROOT, load_cases, load_conflict_cases, load_wish_cases  # noqa: E402

from app.core.budget import SpendGuard  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.providers.local_routing import LocalRouting, load_graph  # noqa: E402
from app.providers.snapshot_places import SnapshotPlaces, load_snapshot  # noqa: E402
from app.services.explain import rank_candidates  # noqa: E402
from app.services.intent import combined_intent, default_negotiation, negotiate  # noqa: E402
from app.services.planner import MAX_GAP_MIN, VIBE_TESTS, plan_for_two, time_slack  # noqa: E402
from app.services.wishes import Wish, interpret_wishes, keyword_wishes, requirement_status  # noqa: E402

NYC = ZoneInfo("America/New_York")
ARMS = ("a", "a2", "b")
ARM_NAMES = {"a": "(a) structured", "a2": "(a') keywords", "b": "(b) Meta"}


def reference_status(case, plan, top) -> dict[str, int]:
    """How the top pick does on the hand-written expected wishes."""
    counts = {"met": 0, "unknown": 0, "not met": 0}
    if top is None:
        return counts
    meet, dest = plan.places[top.meeting_place_id], plan.places[top.endpoint_place_id]
    for who, key in case["expected_wishes"]:
        status = requirement_status(Wish(requirement=key, who=who, quote="-"), meet, dest)
        counts["met" if status is True else "not met" if status is False else "unknown"] += 1
    return counts


CROWD_CLAIM = re.compile(r"\b(crowd(?:s|ed)?|busy|bustling|packed|empty|uncrowded|calm(?:er)?|quiet(?:er)?)\b", re.I)


def hard_ok(top, combined) -> bool | None:
    if top is None:
        return None
    return top.arrival_gap_min <= MAX_GAP_MIN and top.total_elapsed_min <= combined.duration_min + time_slack(combined)


def person_prefs(intent, plan, top) -> tuple[int, int]:
    """(met, checkable) for one person's destination type and vibes on the top pick."""
    if top is None:
        return 0, 0
    meet, dest = plan.places[top.meeting_place_id], plan.places[top.endpoint_place_id]
    checks = []
    if intent.endpoint_type:
        checks.append(dest.category == intent.endpoint_type)
    for vibe in intent.vibes:
        if vibe in VIBE_TESTS:
            checks.append(VIBE_TESTS[vibe](meet) or VIBE_TESTS[vibe](dest))
    return sum(checks), len(checks)


def crowd_claims(text: str) -> list[str]:
    """Crowd-level words that are not part of a stated preference ("A wants to avoid crowds")."""
    from app.services.grounding import _is_preference_mention

    return [m.group(0) for m in CROWD_CLAIM.finditer(text or "")
            if not _is_preference_mention(text, m.start(), m.end())]


def extraction(found, expected) -> tuple[int, int, int]:
    got = {(w.who, w.requirement) for w in found.items}
    exp = set(expected)
    return len(got & exp), len(got - exp), len(exp - got)  # true pos, false pos, missed


STRICT_WORDS = re.compile(r"\b(only|must|at most|no more than|have to be back|need to be back)\b", re.I)


def run(case, places, graph) -> dict:
    a, b = case["intent"], case["b_intent"]
    budget = combined_intent(a, b).duration_min
    # Strict time limits, detected per arm: (a) none, (a') keywords, (b) Muse Spark reading the text.
    from app.services.intent import parse_intent

    strict = {
        "a": (False, False),
        "a2": (bool(STRICT_WORDS.search(case["a_text"])), bool(STRICT_WORDS.search(case["b_text"]))),
        "b": (parse_intent(case["a_text"]).intent.duration_strict if case["a_text"] else False,
              parse_intent(case["b_text"]).intent.duration_strict if case["b_text"] else False),
    }
    det = default_negotiation(a, b, "ablation_baseline")
    kw = keyword_wishes(case["a_text"], case["b_text"])
    neg = negotiate(a, b)
    meta_wishes = interpret_wishes(case["a_text"], case["b_text"])

    out = {"case": case, "budget": budget, "joint": neg.joint, "wishes": {"a2": kw, "b": meta_wishes}}
    for arm, joint, wishes in (("a", det.joint, None), ("a2", det.joint, kw), ("b", neg.joint, meta_wishes)):
        a_arm = a.model_copy(update={"duration_strict": strict[arm][0]})
        b_arm = b.model_copy(update={"duration_strict": strict[arm][1]})
        plan = plan_for_two(case["a"], case["b"], a_arm, b_arm, joint, places, LocalRouting(graph),
                            case["depart_at"], wishes=wishes)
        reason, source = None, "deterministic"
        top = plan.candidates[0] if plan.candidates else None
        if arm == "b" and top is not None:
            ranking = rank_candidates(plan, a, b, joint, wishes)
            top = ranking.candidates[0]
            reason = ranking.reasons.get(top.id)
            source = ranking.source + (f" ({ranking.note})" if ranking.note and ranking.source != "meta" else "")
        out[arm] = {
            "plan": plan, "top": top, "rank_source": source,
            "pick": (f"{plan.places[top.meeting_place_id].name} → {plan.places[top.endpoint_place_id].name}"
                     if top else f"– ({plan.status})"),
            "gap": top.arrival_gap_min if top else None,
            "err": abs(top.total_elapsed_min - budget) if top else None,
            "why": reason or (top.rationale if top else "–"),
            "ref": reference_status(case, plan, top),
            "hard": hard_ok(top, combined_intent(a, b)),  # pre-registered rule: shorter budget + 3 min
            "within_budget": (top.total_elapsed_min <= budget) if top else None,
            "strict": strict[arm],
            "a_pref": person_prefs(a, plan, top),
            "b_pref": person_prefs(b, plan, top),
        }
    out["claims"] = crowd_claims(neg.tradeoff + " " + out["b"]["why"])
    out["neg_source"] = neg.source + (f" ({neg.note})" if neg.note and neg.source != "meta" else "")
    out["tradeoff"] = neg.tradeoff
    return out


def fmt(x):
    return "–" if x is None else f"{x:.1f} min"


def ref_str(r):
    return f"{r['met']} met, {r['unknown']} unknown, {r['not met']} not met"


def report(rows, spend) -> str:
    now = datetime.now(NYC)
    med = lambda xs: statistics.median(xs) if xs else None  # noqa: E731
    # Compared by place names (meeting point -> destination), not OSM ids: another branch of the
    # same chain or another gate of the same park does not count as a different pick.
    ids = lambda r, arm: r[arm]["pick"] if r[arm]["top"] else None  # noqa: E731
    total_ref = sum(len(r["case"]["expected_wishes"]) for r in rows)

    def ref_total(arm, key):
        return sum(r[arm]["ref"][key] for r in rows)

    def extract_total(arm):
        tp = fp = fn = 0
        for r in rows:
            t, f, n = extraction(r["wishes"][arm], r["case"]["expected_wishes"])
            tp, fp, fn = tp + t, fp + f, fn + n
        return tp, fp, fn

    kw_tp, kw_fp, kw_fn = extract_total("a2")
    m_tp, m_fp, m_fn = extract_total("b")
    lines = [
        f"# Meta ablation {now:%Y-%m-%d}",
        "",
        f"- Run: {now:%Y-%m-%d %H:%M} ET; local OSM engine; {len(rows)} cases where A and B want different "
        "things and typed free text (fixtures/benchmark_cases.json: b_intent, a_text, b_text).",
        "- Hard constraints are identical in every arm: the shorter time budget, gap <= 5 min, both avoid lists.",
        "- (a) structured: rule-based merge of both parsed preferences, deterministic ranking.",
        "- (a') keywords: (a) plus wishes a plain keyword matcher finds in the free text.",
        "- (b) Meta: Muse Spark negotiation, Muse Spark wishes (menu-limited, each backed by a quote from "
        "the person's text) in the fit term and destination shortlist, Muse Spark ranking of the top 3. "
        "Model text failing the grounding checks is replaced by deterministic text (marked below).",
        "- Reference: expected_wishes, written by hand before the run. 'Unknown' means OpenStreetMap has no "
        "tag for it at that place; it is never counted as met.",
        "",
        "## Summary",
        "",
        "| Metric | (a) structured | (a') keywords | (b) Meta |",
        "| --- | --- | --- | --- |",
        f"| Reference wishes met by the top pick (of {total_ref}) | {ref_total('a', 'met')} | "
        f"{ref_total('a2', 'met')} | {ref_total('b', 'met')} |",
        f"| … unknown / not met | {ref_total('a', 'unknown')} / {ref_total('a', 'not met')} | "
        f"{ref_total('a2', 'unknown')} / {ref_total('a2', 'not met')} | "
        f"{ref_total('b', 'unknown')} / {ref_total('b', 'not met')} |",
        f"| Wishes extracted correctly (of {total_ref}) / false extra | – | {kw_tp} / {kw_fp} | {m_tp} / {m_fp} |",
        f"| Top pick differs from (a) | – | {sum(ids(r, 'a2') != ids(r, 'a') for r in rows)}/{len(rows)} | "
        f"{sum(ids(r, 'b') != ids(r, 'a') for r in rows)}/{len(rows)} |",
        f"| Top pick differs from (a') | – | – | {sum(ids(r, 'b') != ids(r, 'a2') for r in rows)}/{len(rows)} |",
        f"| Arrival gap, median | " + " | ".join(fmt(med([r[x]['gap'] for r in rows if r[x]['gap'] is not None]))
                                           for x in ARMS) + " |",
        f"| Time-budget error, median | " + " | ".join(fmt(med([r[x]['err'] for r in rows if r[x]['err'] is not None]))
                                                  for x in ARMS) + " |",
        "| Hard constraints met for both people | " + " | ".join(
            f"{sum(r[x]['hard'] is True for r in rows)}/{len(rows)}" for x in ARMS) + " |",
        "| Checkable preferences met, A · B | " + " | ".join(
            f"{sum(r[x]['a_pref'][0] for r in rows)}/{sum(r[x]['a_pref'][1] for r in rows)} · "
            f"{sum(r[x]['b_pref'][0] for r in rows)}/{sum(r[x]['b_pref'][1] for r in rows)}" for x in ARMS) + " |",
        f"| Ungrounded crowd-level words in Meta text | – | – | {sum(len(r['claims']) for r in rows)} |",
        f"| Meta spend for this run | – | – | ${spend:.4f} |",
        "",
        "## Cases",
    ]
    for r in rows:
        c = r["case"]
        kw = ", ".join(f"{w.who}:{w.requirement}" for w in r["wishes"]["a2"].items) or "none"
        mw = ", ".join(f"{w.who}:{w.requirement} (“{w.quote}”)" for w in r["wishes"]["b"].items) or "none"
        exp = ", ".join(f"{who}:{key}" for who, key in c["expected_wishes"])
        lines += [
            "",
            f"### {c['id']}: {c['pair']['a']['name']} ↔ {c['pair']['b']['name']}",
            "",
            f"- A typed: “{c['a_text']}”",
            f"- B typed: “{c['b_text']}”",
            f"- Reference wishes: {exp}",
            f"- Keyword wishes: {kw}",
            f"- Muse Spark wishes: {mw}" + (f" [{r['wishes']['b'].note}]" if r["wishes"]["b"].note else ""),
            f"- Muse Spark negotiation ({r['neg_source']}): {r['tradeoff']}",
            "",
            "| | " + " | ".join(ARM_NAMES[x] for x in ARMS) + " |",
            "| --- | --- | --- | --- |",
            "| Top pick | " + " | ".join(r[x]["pick"] for x in ARMS) + " |",
            "| Reference wishes | " + " | ".join(ref_str(r[x]["ref"]) for x in ARMS) + " |",
            "| Gap / time error | " + " | ".join(f"{fmt(r[x]['gap'])} / {fmt(r[x]['err'])}" for x in ARMS) + " |",
            "| Why this one | " + " | ".join(r[x]["why"] for x in ARMS) + " |",
            "| Ranking | " + " | ".join(r[x]["rank_source"] for x in ARMS) + " |",
            "| Notes shown to users | " + " | ".join(" ".join(r[x]["plan"].notes) or "–" for x in ARMS) + " |",
            "| Hard constraints, both people | " + " | ".join(
                {True: "ok", False: "VIOLATED", None: "–"}[r[x]["hard"]] for x in ARMS) + " |",
            "| Strict time limit detected (A, B) | " + " | ".join(
                f"{'yes' if r[x]['strict'][0] else 'no'}, {'yes' if r[x]['strict'][1] else 'no'}" for x in ARMS) + " |",
            "| Within the shorter budget, no tolerance (added after pre-registration) | " + " | ".join(
                {True: "yes", False: "no", None: "–"}[r[x]["within_budget"]] for x in ARMS) + " |",
            "| A's / B's checkable preferences met | " + " | ".join(
                f"{r[x]['a_pref'][0]}/{r[x]['a_pref'][1]} · {r[x]['b_pref'][0]}/{r[x]['b_pref'][1]}" for x in ARMS) + " |",
        ]
        if r["claims"]:
            lines.append(f"\nUngrounded crowd-level words in Meta text: {', '.join(r['claims'])}")
    lines += ["", "## For human review", "",
              "For each case: which top pick would A and B choose, and is the Meta explanation accurate?"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wish-cases", action="store_true")
    parser.add_argument("--conflict-cases", action="store_true")
    parser.add_argument("--effort", help="reasoning effort for every Muse Spark call (default: settings)")
    args = parser.parse_args()
    s = get_settings()
    if args.effort:
        from app.core.config import reasoning_override

        reasoning_override.set(args.effort)
    places, graph = SnapshotPlaces(load_snapshot(s.places_snapshot_path)), load_graph(s.graph_path)
    guard = SpendGuard()
    before = guard.today_total()
    rows = []
    cases = load_wish_cases() if args.wish_cases else load_conflict_cases() if args.conflict_cases else load_cases()
    for case in cases:
        if case["b_intent"] is None or not case["a_text"]:
            continue
        row = run(case, places, graph)
        print(f"{case['id']}: a={row['a']['pick']} | a'={row['a2']['pick']} | b={row['b']['pick']} | "
              f"ref met a/a'/b = {row['a']['ref']['met']}/{row['a2']['ref']['met']}/{row['b']['ref']['met']}")
        rows.append(row)
    suffix = "-ablation-wishes" if args.wish_cases else "-ablation-conflicts" if args.conflict_cases else "-ablation"
    suffix += f"-{args.effort}" if args.effort else ""
    out = ROOT / "benchmarks" / f"{datetime.now(NYC):%Y-%m-%d}{suffix}.md"
    text = report(rows, guard.today_total() - before)
    if args.conflict_cases:
        text = text.replace("cases where A and B want different things and typed free text "
                            "(fixtures/benchmark_cases.json: b_intent, a_text, b_text)",
                            "pre-registered A-vs-B conflict cases (fixtures/conflict_cases.json, committed "
                            "before this run; evaluation rules in its _rule field)")
    if args.wish_cases:
        text = text.replace("cases where A and B want different things and typed free text "
                            "(fixtures/benchmark_cases.json: b_intent, a_text, b_text)",
                            "pre-registered wish cases (fixtures/wish_cases.json, rule in "
                            "scripts/make_wish_cases.py, committed before this run)")
    out.write_text(text)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
