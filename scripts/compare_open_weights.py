"""Side by side: open-weights evaluation runs, from their saved outputs (sample_outputs/open_weights/run<N>/),
scored by scripts/eval_open_weights.py's own summary. Void runs are listed with their reason, not scored.

    python scripts/compare_open_weights.py 1 3      # writes benchmarks/open-weights-runs-1-3.md
"""

import json
import sys

from _common import ROOT

from eval_open_weights import CUTOFF_S, summary  # noqa: E402

VOID = {2: "SGLang's grammar engine (xgrammar) rejected the uniqueItems keyword added with the fix: "
           "HTTP 400 on every Glimmer wish-reading request, so the model was never reached. "
           "Committed as is; the fix was corrected to maxItems only."}
FIX = {3: "every list in the schema Glimmer decodes against bounded with maxItems (inferred_fields at most 5, "
          "other lists at most 8). No prompt change."}


def load(run: int) -> dict:
    d = ROOT / "sample_outputs" / "open_weights" / f"run{run}"
    res = {m: {"parses": {}, "wishes": {}} for m in ("glimmer", "spark")}
    for f in sorted(d.glob("parse_*.json")):
        x = json.loads(f.read_text())
        res["glimmer"]["parses"][x["text"]] = x["muse_glimmer"]
        res["spark"]["parses"][x["text"]] = x["muse_spark_1_3"]
    for f in sorted(d.glob("wishes_*.json")):
        x = json.loads(f.read_text())
        res["glimmer"]["wishes"][x["case"]] = x["muse_glimmer"]
        res["spark"]["wishes"][x["case"]] = x["muse_spark_1_3"]
    return res


def main() -> int:
    runs = [int(a) for a in sys.argv[1:]]
    if not runs:
        print(__doc__)
        return 1
    scored = {r: {m: summary(v) for m, v in load(r).items()} for r in runs if r not in VOID}
    cols = [(r, m) for r in scored for m in ("glimmer", "spark")]
    name = {"glimmer": "Glimmer", "spark": "Spark"}
    head = "| | " + " | ".join(f"Run {r} {name[m]}" for r, m in cols) + " |"
    rows = [
        ("Valid WalkIntent", lambda x: f"{x['intent_valid']}/{x['n']}"),
        ("Duration right", lambda x: f"{x['duration'][0]}/{x['duration'][1]}"),
        ("Ending right (scored texts)", lambda x: f"{x['endpoint'][0]}/{x['endpoint'][1]}"),
        ("Latency median / max", lambda x: f"{x['p50']:.2f} s / {x['max']:.2f} s"),
        (f"Within {CUTOFF_S:.0f} s", lambda x: f"{x['within']}/{x['n']}"),
        ("Cost per parse", lambda x: f"${x['cost']:.5f}"),
        ("Wish recognition found / extra", lambda x: f"{x['wish_found']}/{x['wish_expected']} / {x['wish_extra']}"),
    ]
    lines = [f"# Open-weights evaluation: runs {', '.join(map(str, runs))} side by side", "",
             "Same pre-registered cases and scoring (scripts/eval_open_weights.py). Glimmer: "
             "meta-models/Muse-Glimmer-30B@f84ecc3, BF16, Modal, 1x H200, reasoning off. "
             "Muse Spark: muse-spark-1.3, effort minimal.", ""]
    for r in runs:
        if r in VOID:
            lines.append(f"- Run {r}: **void**. {VOID[r]}")
        elif r in FIX:
            lines.append(f"- Run {r}: after run 1, {FIX[r]}")
        else:
            lines.append(f"- Run {r}: baseline, reported as is.")
    lines += ["", head, "| --- |" + " --- |" * len(cols)]
    lines += [f"| {label} | " + " | ".join(f(scored[r][m]) for r, m in cols) + " |" for label, f in rows]
    lines += ["", "Wish recognition stays on Muse Spark in the app; Glimmer only reads the wish (WalkIntent).", ""]
    out = ROOT / "benchmarks" / f"open-weights-runs-{'-'.join(map(str, runs))}.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
