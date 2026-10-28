"""Meta ablation: does Muse Spark negotiation + ranking change the plan, and how?

    python scripts/ablation.py

For every benchmark case with a B preference (each conflicts with A's), on the local engine:
  (a) deterministic: rule-based merge of both preferences, deterministic ranking (rung 2)
  (b) Meta: Muse Spark negotiate() -> JointPreference used in the fit term, then Muse Spark
      ranks the top 3 (rung 1); grounding checks may reject model text (shown in the report).
Writes benchmarks/YYYY-MM-DD-ablation.md with both explanations side by side for human review.
"""

import os
import statistics
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ["USE_MOCKS"] = "false"

from _common import ROOT, load_cases  # noqa: E402

from app.core.budget import SpendGuard  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.providers.local_routing import LocalRouting, load_graph  # noqa: E402
from app.providers.snapshot_places import SnapshotPlaces, load_snapshot  # noqa: E402
from app.services.explain import rank_candidates  # noqa: E402
from app.services.intent import combined_intent, default_negotiation, negotiate  # noqa: E402
from app.services.planner import plan_for_two  # noqa: E402

NYC = ZoneInfo("America/New_York")


def describe(result, c) -> str:
    p = result.places
    return f"{p[c.meeting_place_id].name} → {p[c.endpoint_place_id].name} ({p[c.endpoint_place_id].category})"


def run(case, places, routing) -> dict:
    a, b = case["intent"], case["b_intent"]
    budget = combined_intent(a, b).duration_min

    det_neg = default_negotiation(a, b, "ablation_baseline")
    det = plan_for_two(case["a"], case["b"], a, b, det_neg.joint, places, routing, case["depart_at"])
    det_top = det.candidates[0] if det.candidates else None

    neg = negotiate(a, b)
    meta_plan = plan_for_two(case["a"], case["b"], a, b, neg.joint, places, routing, case["depart_at"])
    ranking = rank_candidates(meta_plan, a, b, neg.joint)
    meta_top = ranking.candidates[0] if ranking.candidates else None

    def summary(plan, top, reason, neg_obj, rank_src):
        if top is None:
            return {"status": plan.status, "pick": "–", "gap": None, "err": None, "why": "–",
                    "tradeoff": neg_obj.tradeoff, "sources": f"negotiation {neg_obj.source}"}
        return {
            "status": plan.status, "pick": describe(plan, top), "id": top.id,
            "gap": top.arrival_gap_min, "err": abs(top.total_elapsed_min - budget),
            "why": reason or top.rationale, "tradeoff": neg_obj.tradeoff,
            "sources": f"negotiation {neg_obj.source}{' (' + neg_obj.note + ')' if neg_obj.note and neg_obj.source != 'meta' else ''}, ranking {rank_src}",
        }

    det_row = summary(det, det_top, None, det_neg, "deterministic")
    meta_reason = ranking.reasons.get(meta_top.id) if meta_top else None
    rank_src = ranking.source + (f" ({ranking.note})" if ranking.note and ranking.source != "meta" else "")
    meta_row = summary(meta_plan, meta_top, meta_reason, neg, rank_src)
    changed = det_top is not None and meta_top is not None and det_top.id != meta_top.id
    return {"case": case, "budget": budget, "det": det_row, "meta": meta_row, "changed": changed,
            "joint": neg.joint}


def fmt(x):
    return "–" if x is None else f"{x:.1f} min"


def report(rows, spend) -> str:
    now = datetime.now(NYC)
    changed = sum(r["changed"] for r in rows)
    both = [r for r in rows if r["det"]["gap"] is not None and r["meta"]["gap"] is not None]
    med = lambda xs: statistics.median(xs) if xs else None  # noqa: E731
    lines = [
        f"# Meta ablation {now:%Y-%m-%d}",
        "",
        f"- Run: {now:%Y-%m-%d %H:%M} ET; local OSM engine; cases with a conflicting B preference "
        "(fixtures/benchmark_cases.json, b_intent).",
        "- (a) deterministic: rule-based merge of both preferences, deterministic ranking.",
        "- (b) Meta: Muse Spark negotiation feeds the fit term, Muse Spark ranks the top 3. Model text "
        "that fails the grounding checks is replaced by the deterministic text (marked below).",
        "- Hard constraints (time budget = shorter of the two, gap <= 5 min, avoid lists) are identical in (a) and (b).",
        "",
        "## Summary",
        "",
        "| Metric | (a) deterministic | (b) Meta |",
        "| --- | --- | --- |",
        f"| Top pick differs from (a) | – | {changed}/{len(rows)} |",
        f"| Arrival gap, median | {fmt(med([r['det']['gap'] for r in both]))} | {fmt(med([r['meta']['gap'] for r in both]))} |",
        f"| Time-budget error, median | {fmt(med([r['det']['err'] for r in both]))} | {fmt(med([r['meta']['err'] for r in both]))} |",
        f"| Meta spend for this run | – | ${spend:.4f} |",
        "",
        "## Cases",
    ]
    for r in rows:
        c, d, m = r["case"], r["det"], r["meta"]
        a, b = c["intent"], c["b_intent"]
        lines += [
            "",
            f"### {c['id']}: {c['pair']['a']['name']} ↔ {c['pair']['b']['name']} "
            f"({'top pick changed' if r['changed'] else 'same top pick'})",
            "",
            f"- A: {a.model_dump(exclude_defaults=True)}",
            f"- B: {b.model_dump(exclude_defaults=True)}",
            f"- Meta joint preference: {r['joint'].model_dump()}",
            "",
            "| | (a) deterministic | (b) Meta |",
            "| --- | --- | --- |",
            f"| Top pick | {d['pick']} | {m['pick']} |",
            f"| Gap / time error | {fmt(d['gap'])} / {fmt(d['err'])} | {fmt(m['gap'])} / {fmt(m['err'])} |",
            f"| Why this one | {d['why']} | {m['why']} |",
            f"| Trade-off | {d['tradeoff']} | {m['tradeoff']} |",
            f"| Sources | {d['sources']} | {m['sources']} |",
        ]
    lines += ["", "## For human review", "",
              "For each case: which top pick would you choose, (a) or (b), and is the explanation accurate?"]
    return "\n".join(lines) + "\n"


def main() -> int:
    s = get_settings()
    places, graph = SnapshotPlaces(load_snapshot(s.places_snapshot_path)), load_graph(s.graph_path)
    guard = SpendGuard()
    before = guard.today_total()
    rows = []
    for case in load_cases():
        if case["b_intent"] is None:
            continue
        row = run(case, places, LocalRouting(graph))
        print(f"{case['id']}: {'changed' if row['changed'] else 'same'} | a: {row['det']['pick']} | b: {row['meta']['pick']}")
        rows.append(row)
    out = ROOT / "benchmarks" / f"{datetime.now(NYC):%Y-%m-%d}-ablation.md"
    out.write_text(report(rows, guard.today_total() - before))
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
