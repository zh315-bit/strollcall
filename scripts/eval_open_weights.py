"""Muse Glimmer (open weights, our Modal endpoint) vs muse-spark-1.3 (Meta API) on the
pre-registered wish cases. Pre-registered: this file (cases, expected values, scoring) is
committed before the first run, and the first run is reported as is.

    python scripts/glimmer_warm.py --no-site --minutes 10   # in another terminal, first
    python scripts/eval_open_weights.py --run 1

Cases: fixtures/wish_cases.json (pre-registered 2026-10-28, rule in scripts/make_wish_cases.py).
Only their own texts are sent to either model; no coordinates.

Two jobs, both with the production prompts and schemas, unchanged:
1. Wish reading (services/intent.py: SYSTEM_PROMPT, INTENT_SCHEMA), the job Glimmer will do in
   the app, once per distinct text (12 texts). Scored:
   - JSON valid: the reply is one JSON object;
   - intent valid: it validates as WalkIntent (the app's own check);
   - duration: 30 for the texts that say "30 minutes", otherwise the default 25 with
     "duration_min" listed in inferred_fields;
   - endpoint: "cafe" for texts that name coffee or a cafe, null for "Somewhere nice, about 30
     minutes"; other texts are not scored on endpoint (EXPECTED_ENDPOINT below, written by hand
     before the run);
   - latency (wall clock, one request at a time, endpoint already warm), and how many answers
     came within the app's 3 s fallback limit;
   - cost per parse: Muse Spark from its token usage and Meta's prices (the spend guard);
     Glimmer as its share of the warm GPU (latency x $4.86/h), since Modal bills per second.
2. Wish recognition (services/wishes.py: the menu-limited, quoted wishes), once per case
   (10 cases), scored against each case's expected_wishes (hand-written before any run):
   expected found, and extra wishes not expected.

Settings: Muse Spark at the effort the page uses for wish reading (accept_reasoning_effort,
"minimal"). Glimmer with reasoning off (the prompt opens its answer channel, see
providers/glimmer.answer_prompt), temperature 0, JSON constrained by SGLang; 30 s timeout here so
slow answers are measured rather than cut off.
One pass per model, Glimmer first, then Muse Spark.

Writes benchmarks/<date>-open-weights-run<N>.md and sample_outputs/open_weights/run<N>/: one file
per text and per case with each model's raw output and the validated result side by side, and
run_log.txt with one line per Glimmer call (model, precision, host, GPU, deployment, latency).
"""

import argparse
import json
import sys
import time
from datetime import date

from _common import ROOT

from pydantic import ValidationError

import app.providers as providers
from app.core.budget import SpendGuard
from app.core.config import get_settings, output_cap_override, reasoning_override
from app.core.errors import ProviderError
from app.models.schemas import WalkIntent
from app.providers.glimmer import GlimmerProvider, deployment
from app.providers.meta import MetaProvider
from app.services.intent import INTENT_SCHEMA, SYSTEM_PROMPT
from app.services.wishes import interpret_wishes

CUTOFF_S = 3.0
NEUTRAL_B = "Somewhere nice, about 30 minutes"
# Hand-written before the first run: texts that name coffee or a cafe end at a cafe; the neutral
# line names no ending. Texts not listed here are not scored on endpoint.
EXPECTED_ENDPOINT = {
    "It's warm out, let's get a coffee we can drink sitting outside": "cafe",
    "A coffee on a patio in the sun would be perfect": "cafe",
    "Anywhere for coffee as long as it's not Starbucks": "cafe",
    "I use a wheelchair, so the cafe has to work for that": "cafe",
    "Coffee at the end, about 30 minutes": "cafe",
    NEUTRAL_B: None,
}


def expected_duration(text: str) -> int:
    return 30 if "30 minutes" in text else 25


def texts_and_cases() -> tuple[list[str], list[dict]]:
    cases = json.loads((ROOT / "fixtures" / "wish_cases.json").read_text())["cases"]
    texts: list[str] = []
    for c in cases:
        for t in (c["a_text"], c["b_text"]):
            if t not in texts:
                texts.append(t)
    return texts, cases


def parse_with(provider, text: str, guard: SpendGuard) -> dict:
    before = guard.today_total()
    t = time.monotonic()
    out = {"raw": None, "json_valid": False, "intent": None, "intent_valid": False, "error": None}
    token = output_cap_override.set(get_settings().parse_max_output_tokens)
    try:
        data = provider.structured_json(SYSTEM_PROMPT, f"Walk description:\n{text}", INTENT_SCHEMA,
                                        name="walk_intent")
        out["json_valid"] = True
        out["raw"] = getattr(provider, "last_call", {}).get("content") or json.dumps(data)
        try:
            out["intent"] = WalkIntent.model_validate(data).model_dump()
            out["inferred_fields"] = data.get("inferred_fields", [])
            out["intent_valid"] = True
        except ValidationError as e:
            out["error"] = f"WalkIntent validation: {e.error_count()} errors"
    except ProviderError as e:
        out["error"] = f"{e.code}: {e.message}"
        out["raw"] = getattr(provider, "last_call", {}).get("content")
        out["json_valid"] = out["raw"] is not None and _is_json(out["raw"])
    finally:
        output_cap_override.reset(token)
    out["latency_s"] = round(time.monotonic() - t, 3)
    out["cost_usd"] = round(guard.today_total() - before, 6)
    if hasattr(provider, "last_call"):
        out["glimmer"] = {k: provider.last_call.get(k) for k in
                          ("prompt_tokens", "completion_tokens", "reasoning_chars", "finish_reason")}
    return out


def _is_json(s: str) -> bool:
    try:
        return isinstance(json.loads(s), dict)
    except ValueError:
        return False


def score_parse(text: str, r: dict) -> dict:
    sc = {"duration": None, "endpoint": None}
    if r["intent_valid"]:
        want = expected_duration(text)
        got = r["intent"]["duration_min"]
        sc["duration"] = got == want and (want == 30 or "duration_min" in r.get("inferred_fields", []))
        if text in EXPECTED_ENDPOINT:
            sc["endpoint"] = r["intent"]["endpoint_type"] == EXPECTED_ENDPOINT[text]
    return sc


def wishes_with(provider, case: dict, guard: SpendGuard) -> dict:
    before = guard.today_total()
    real = providers.get_meta
    providers.get_meta = lambda kind="text": provider
    t = time.monotonic()
    try:
        w = interpret_wishes(case["a_text"], case["b_text"])
    finally:
        providers.get_meta = real
    found = [[x.who, x.requirement] for x in w.items]
    expected = case["expected_wishes"]
    return {"wishes": [x.model_dump() for x in w.items], "source": w.source, "note": w.note,
            "raw": getattr(provider, "last_call", {}).get("content"),
            "latency_s": round(time.monotonic() - t, 3), "cost_usd": round(guard.today_total() - before, 6),
            "expected_found": sum(1 for e in expected if e in found),
            "expected": len(expected), "extra": sum(1 for f in found if f not in expected)}


def run_model(name: str, provider, texts, cases, guard) -> dict:
    parses, wishes = {}, {}
    for i, text in enumerate(texts, 1):
        r = parse_with(provider, text, guard)
        r["score"] = score_parse(text, r)
        parses[text] = r
        print(f"  [{name}] parse {i}/{len(texts)} {r['latency_s']:.2f}s valid={r['intent_valid']} {r['score']}")
    for c in cases:
        wishes[c["id"]] = w = wishes_with(provider, c, guard)
        print(f"  [{name}] wishes {c['id']} {w['latency_s']:.2f}s found {w['expected_found']}/{w['expected']} "
              f"extra {w['extra']} ({w['source']})")
    return {"parses": parses, "wishes": wishes}


def summary(res: dict) -> dict:
    ps = list(res["parses"].values())
    lat = sorted(p["latency_s"] for p in ps)
    scored = lambda k: [p["score"][k] for p in ps if p["score"][k] is not None]  # noqa: E731
    ws = list(res["wishes"].values())
    return {
        "n": len(ps), "json_valid": sum(p["json_valid"] for p in ps), "intent_valid": sum(p["intent_valid"] for p in ps),
        "duration": (sum(scored("duration")), len([p for p in ps if p["intent_valid"]])),
        "endpoint": (sum(scored("endpoint")), len(scored("endpoint"))),
        "p50": lat[len(lat) // 2], "max": lat[-1], "within": sum(x <= CUTOFF_S for x in lat),
        "cost": sum(p["cost_usd"] for p in ps) / len(ps),
        "wish_found": sum(w["expected_found"] for w in ws), "wish_expected": sum(w["expected"] for w in ws),
        "wish_extra": sum(w["extra"] for w in ws), "wish_ok": sum(w["source"] not in ("default", "mock") for w in ws),
        "wish_cost": sum(w["cost_usd"] for w in ws) / len(ws),
    }


def report(run: int, res: dict, glimmer_log: list[str]) -> str:
    s = get_settings()
    g, m = summary(res["glimmer"]), summary(res["spark"])
    d = deployment(s)
    row = lambda label, f: f"| {label} | {f(g)} | {f(m)} |"  # noqa: E731
    lines = [
        f"# Open-weights evaluation, run {run}: Muse Glimmer vs muse-spark-1.3 ({date.today().isoformat()})",
        "",
        f"- Glimmer: `{d['repo']}@{d['revision']}`, {d['precision']}, Modal Dedicated Endpoint "
        f"`{d['deployment']}` (SGLang), 1x {d['gpu']}, reasoning off (answer channel), temperature 0.",
        f"- Muse Spark: `{s.model_id}` on the Meta Model API, reasoning effort `{s.accept_reasoning_effort}`.",
        "- Cases: fixtures/wish_cases.json (pre-registered); scoring and expected values in "
        "scripts/eval_open_weights.py, committed before this run. Production prompts, unchanged.",
        "- One request at a time; the Glimmer endpoint was warm (scripts/glimmer_warm.py).",
        "",
        "| | Muse Glimmer (open weights, Modal) | muse-spark-1.3 (Meta API) |",
        "| --- | --- | --- |",
        row("Wish reading: JSON valid", lambda x: f"{x['json_valid']}/{x['n']}"),
        row("Wish reading: valid WalkIntent", lambda x: f"{x['intent_valid']}/{x['n']}"),
        row("Duration right", lambda x: f"{x['duration'][0]}/{x['duration'][1]}"),
        row("Ending right (scored texts)", lambda x: f"{x['endpoint'][0]}/{x['endpoint'][1]}"),
        row("Latency, median / max", lambda x: f"{x['p50']:.2f} s / {x['max']:.2f} s"),
        row(f"Within the {CUTOFF_S:.0f} s fallback limit", lambda x: f"{x['within']}/{x['n']}"),
        row("Cost per parse", lambda x: f"${x['cost']:.5f}"),
        row("Wish recognition: expected found", lambda x: f"{x['wish_found']}/{x['wish_expected']}"),
        row("Wish recognition: extra wishes", lambda x: str(x["wish_extra"])),
        row("Wish recognition: answered (not fallback)", lambda x: f"{x['wish_ok']}/{len(res['glimmer']['wishes'])}"),
        row("Cost per wish recognition", lambda x: f"${x['wish_cost']:.5f}"),
        "",
        "Glimmer's cost per parse is its share of the warm GPU (latency x $4.86/h). A warm window "
        "also bills the cold start (~3.3 min, ~$0.27) and 2 idle minutes after the last call (~$0.16).",
        "",
        "## Per text (wish reading)",
        "",
        "| Text | Glimmer | Spark |",
        "| --- | --- | --- |",
    ]
    for text in res["glimmer"]["parses"]:
        cell = lambda p: (f"{p['latency_s']:.2f}s, " + (  # noqa: E731
            f"{p['intent']['duration_min']} min, {p['intent']['endpoint_type']}, vibes {p['intent']['vibes']}, "
            f"avoid {p['intent']['avoid']}, hard {p['intent']['hard_constraints']}" if p["intent_valid"] else f"invalid ({p['error']})"))
        lines.append(f"| {text} | {cell(res['glimmer']['parses'][text])} | {cell(res['spark']['parses'][text])} |")
    lines += ["", "## Glimmer run log", "", "```", *glimmer_log, "```", ""]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=int, required=True)
    args = p.parse_args()
    s = get_settings()
    out_dir = ROOT / "sample_outputs" / "open_weights" / f"run{args.run}"
    bench = ROOT / "benchmarks" / f"{date.today().isoformat()}-open-weights-run{args.run}.md"
    if bench.exists() or out_dir.exists():
        print(f"{bench.name} or {out_dir} exists: runs are never overwritten.")
        return 1
    texts, cases = texts_and_cases()
    guard = SpendGuard()
    reasoning_override.set(s.accept_reasoning_effort)

    glimmer = GlimmerProvider(timeout_s=30)
    glimmer_log: list[str] = []
    real_info = glimmer.guard.record

    def record(kind, model, cost, detail=""):
        glimmer_log.append(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {detail}")
        real_info(kind, model, cost, detail)
    glimmer.guard.record = record

    res = {"glimmer": run_model("glimmer", glimmer, texts, cases, guard),
           "spark": run_model("spark", MetaProvider(), texts, cases, guard)}

    out_dir.mkdir(parents=True)
    for i, text in enumerate(texts, 1):
        (out_dir / f"parse_{i:02d}.json").write_text(json.dumps(
            {"text": text, "expected": {"duration_min": expected_duration(text),
                                        "endpoint_type": EXPECTED_ENDPOINT.get(text, "not scored")},
             "muse_glimmer": res["glimmer"]["parses"][text], "muse_spark_1_3": res["spark"]["parses"][text]},
            indent=2, ensure_ascii=False) + "\n")
    for c in cases:
        (out_dir / f"wishes_{c['id']}.json").write_text(json.dumps(
            {"case": c["id"], "a_text": c["a_text"], "b_text": c["b_text"], "expected_wishes": c["expected_wishes"],
             "muse_glimmer": res["glimmer"]["wishes"][c["id"]], "muse_spark_1_3": res["spark"]["wishes"][c["id"]]},
            indent=2, ensure_ascii=False) + "\n")
    (out_dir / "run_log.txt").write_text("\n".join(glimmer_log) + "\n")
    bench.write_text(report(args.run, res, glimmer_log))
    print(f"wrote {bench.relative_to(ROOT)} and {out_dir.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
