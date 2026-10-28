"""Run the planner on the benchmark cases and write benchmarks/YYYY-MM-DD[-engine].md.

    python scripts/benchmark.py                 # local OSM graph + place snapshot (default)
    python scripts/benchmark.py --engine apis   # live Overpass + ORS, warm caches
    python scripts/benchmark.py --engine apis --cold   # cold latency (spends ORS quota:
                                                # about 2 matrix + 9 directions per case)
    python scripts/benchmark.py --mock          # recorded fixtures, offline
    python scripts/benchmark.py --cases p1,p3   # a subset

Each case runs twice with the same providers:
  first  - local: a fresh routing instance (empty search cache, graph already loaded);
           apis with --cold: empty Overpass cache and no ORS cache reads, one attempt;
           apis otherwise: the normal caches (cache/ tiles, ORS SQLite cache);
  cached - the same query again, served from the caches (if the first run failed on
           Overpass, it is retried up to 3 times with a pause before this run so the
           plan itself can still be measured).
Plan metrics (feasibility, gap, time-budget error) use the top candidate of the cached run.
The planner makes no Meta calls (fallback rung 2).
"""

import argparse
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

parser = argparse.ArgumentParser()
parser.add_argument("--mock", action="store_true", help="use recorded fixtures (offline)")
parser.add_argument("--cold", action="store_true", help="measure cold latency (spends ORS quota)")
parser.add_argument("--cases", help="comma-separated case ids, default all")
parser.add_argument("--engine", choices=["local", "apis"], default="local")
ARGS = parser.parse_args()
os.environ["USE_MOCKS"] = "true" if ARGS.mock else "false"

from _common import ROOT, load_cases  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.providers.local_routing import LocalRouting, load_graph  # noqa: E402
from app.providers.mock import MockORS, MockOverpass  # noqa: E402
from app.providers.ors import ORSProvider  # noqa: E402
from app.providers.overpass import OverpassProvider  # noqa: E402
from app.providers.snapshot_places import SnapshotPlaces, load_snapshot  # noqa: E402
from app.services.planner import PlanResult, plan_walk  # noqa: E402

NYC = ZoneInfo("America/New_York")


LOAD: dict = {}


def local_data():
    """Graph and snapshot, loaded once; load time and memory recorded for the report."""
    if not LOAD:
        import psutil

        s, proc = get_settings(), psutil.Process()
        rss0, t = proc.memory_info().rss, time.perf_counter()
        LOAD["graph"], LOAD["snapshot"] = load_graph(s.graph_path), load_snapshot(s.places_snapshot_path)
        LOAD["seconds"], LOAD["rss_mb"] = time.perf_counter() - t, (proc.memory_info().rss - rss0) / 1e6
    return LOAD["graph"], LOAD["snapshot"]


def providers(cache_dir: Path):
    if ARGS.mock:
        return MockOverpass(), MockORS()
    if ARGS.engine == "local":
        graph, snapshot = local_data()
        return SnapshotPlaces(snapshot), LocalRouting(graph)
    update = {"overpass_timeout_s": 60.0}
    if ARGS.cold:
        update["cache_dir"] = cache_dir
    settings = get_settings().model_copy(update=update)
    return OverpassProvider(settings=settings), ORSProvider(disk_cache=not ARGS.cold)


def timed(case, overpass, ors) -> tuple[PlanResult, float]:
    start = time.perf_counter()
    result = plan_walk(case["a"], case["b"], case["intent"], overpass, ors, case["depart_at"])
    return result, time.perf_counter() - start


def run_case(case, cache_dir: Path) -> dict:
    overpass, ors = providers(cache_dir)
    cold, cold_s = timed(case, overpass, ors)
    result = cold
    attempts = 1
    # A cold run that failed on Overpass leaves queries uncached: fetch them (bounded) first,
    # so the cached timing below never includes a fetch.
    while result.status == "places_unavailable" and attempts < 3 and not ARGS.mock and ARGS.engine == "apis":
        time.sleep(30 * attempts)
        attempts += 1
        result, _ = timed(case, overpass, ors)
    cached, cached_s = timed(case, overpass, ors)
    top = cached.candidates[0] if cached.candidates else None
    return {
        "case": case,
        "cold": cold,
        "cold_s": cold_s,
        "cached": cached,
        "cached_s": cached_s,
        "top": top,
        "time_error": abs(top.total_elapsed_min - case["intent"].duration_min) if top else None,
    }


def outcome_ok(row) -> bool:
    expected = row["case"]["expected"]
    status = row["cached"].status
    if expected == "feasible":
        return status == "proposed"
    return status == "no_feasible_plan"  # infeasible by distance: an honest no-plan is correct


def fmt(x, unit="", nd=1):
    return "–" if x is None else f"{x:.{nd}f}{unit}"


def median(xs):
    return statistics.median(xs) if xs else None


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def report(rows: list[dict]) -> str:
    n = len(rows)
    solved = [r for r in rows if r["top"]]
    gaps = [r["top"].arrival_gap_min for r in solved]
    errors = [r["time_error"] for r in solved]
    cold_ok = [r["cold_s"] for r in rows if r["cold"].status not in ("places_unavailable", "routing_unavailable")]
    cached_ok = [r["cached_s"] for r in rows if r["cached"].status not in ("places_unavailable", "routing_unavailable")]
    if ARGS.mock:
        correct = sum(outcome_ok(r) for r in rows)
    mode = "recorded fixtures (USE_MOCKS=true, offline); latencies are fixture reads, not network"
    elif ARGS.engine == "local":
        g, snap = LOAD["graph"], LOAD["snapshot"]
        mode = (f"local OSM walking graph ({len(g.lat):,} nodes, {g.file_bytes / 1e6:.1f} MB) + place snapshot "
                f"(fetched {snap.fetched_at[:10]}); data loaded in {LOAD['seconds']:.2f} s, "
                f"+{LOAD['rss_mb']:.0f} MB RSS; walking speed 80 m/min")
    elif ARGS.cold:
        mode = "live APIs, cold first run (no Overpass or ORS cache)"
    else:
        mode = "live APIs with warm caches (first run may still fetch what is not cached)"
    now = datetime.now(NYC)
    lines = [
        f"# Planner benchmark {now:%Y-%m-%d}",
        "",
        f"- Run: {now:%Y-%m-%d %H:%M} ET, commit `{git_commit()}`, mode: {mode}",
        f"- Cases: fixtures/benchmark_cases.json (departure {rows[0]['case']['depart_at'].isoformat()})",
        "- Planner only, no Meta calls (fallback rung 2). Metrics use each case's top candidate.",
        "- Expected outcome: infeasible by distance when the direct A-B walk exceeds 1.2 x duration "
        "(rule in fixtures/benchmark_cases.json), otherwise feasible.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Feasibility rate | {len(solved)}/{n} ({100 * len(solved) / n:.0f}%) |",
        f"| Correct outcome rate | {correct}/{n} ({100 * correct / n:.0f}%): plan found where expected, "
        f"honest no-plan where the pair is too far apart (see Expected) |",
        f"| Arrival gap, median / max | {fmt(median(gaps), ' min')} / {fmt(max(gaps) if gaps else None, ' min')} |",
        f"| Time-budget error, median | {fmt(median(errors), ' min')} |",
        f"| Planning latency, {'cold' if ARGS.cold else 'first run'}, median | {fmt(median(cold_ok), ' s', 3)} ({len(cold_ok)}/{n} completed) |",
        f"| Planning latency, cached, median | {fmt(median(cached_ok), ' s', 3)} |",
        "",
        "## Cases",
        "",
        "| Case | Origins | Intent | Expected | Status | Meetup → destination | Gap | Elapsed / budget | First run | Cached |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        c, top, res = r["case"], r["top"], r["cached"]
        intent = c["intent"]
        what = f"{intent.duration_min} min, {intent.endpoint_type or 'any'}" + (
            f", {'/'.join(intent.vibes)}" if intent.vibes else "")
        route = (f"{res.places[top.meeting_place_id].name} → {res.places[top.endpoint_place_id].name}"
                 if top else "–")
        failed = r["cold"].status in ("places_unavailable", "routing_unavailable")
        cold = r["cold"].status if failed else fmt(r["cold_s"], " s", 2)
        lines.append(
            f"| {c['id']} | {c['pair']['a']['name']} ↔ {c['pair']['b']['name']} | {what} | "
            f"{c['expected'].replace('_', ' ')} | {res.status}{'' if outcome_ok(r) else ' ✗'} | "
            f"{route} | {fmt(top.arrival_gap_min if top else None, ' min')} | "
            f"{fmt(top.total_elapsed_min if top else None)} / {intent.duration_min} | {cold} | "
            f"{fmt(r['cached_s'], ' s', 3)} |"
        )
    lines += ["", "## Unsolved cases", ""]
    unsolved = [r for r in rows if not r["top"]]
    if not unsolved:
        lines.append("None.")
    for r in unsolved:
        res = r["cached"]
        reason = (f"binding constraint: {res.failure.constraint} ({res.failure.count} candidates removed). "
                  f"Suggestion{' (verified by replanning)' if res.failure.verified else ''}: {res.failure.suggestion}"
                  if res.failure else res.error or "")
        reason += f" Expected: {r['case']['expected'].replace('_', ' ')}."
        lines.append(f"- **{r['case']['id']}**: {res.status}. {reason}")
    cold_failed = [r for r in rows if r["cold"].status in ("places_unavailable", "routing_unavailable")]
    if cold_failed:
        lines += ["", "## First-run provider failures", ""]
        for r in cold_failed:
            lines.append(f"- {r['case']['id']}: {r['cold'].status} ({r['cold'].error})")
    lines += ["", "## Filter counts (cached run)", ""]
    for r in rows:
        stats = ", ".join(f"{k}={v}" for k, v in sorted(r["cached"].stats.items()))
        lines.append(f"- {r['case']['id']}: {stats or '–'}")
    return "\n".join(lines) + "\n"


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        wanted = set(ARGS.cases.split(",")) if ARGS.cases else None
        for case in load_cases():
            if wanted and case["id"] not in wanted:
                continue
            row = run_case(case, Path(tmp))
            print(f"{case['id']}: cold {row['cold'].status} {row['cold_s']:.2f}s, cached {row['cached'].status} {row['cached_s']:.3f}s")
            rows.append(row)
    out_dir = ROOT / "benchmarks"
    out_dir.mkdir(exist_ok=True)
    suffix = ("-mock" if ARGS.mock else f"-{ARGS.engine}") + (f"-{ARGS.cases.replace(',', '')}" if ARGS.cases else "")
    out = out_dir / f"{datetime.now(NYC):%Y-%m-%d}{suffix}.md"
    out.write_text(report(rows))
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
