"""User-test report (DEV_DOC section 9) from the invites and after-walk survey in the database.

    DATABASE_URL=... python scripts/user_test_report.py --since 2026-11-02 [--until 2026-11-04] [--out FILE.md]

Without DATABASE_URL it reads the local SQLite database. Prints Markdown: the invite funnel
(created -> opened by B -> accepted -> planned -> confirmed), time from invite to acceptance,
planning time, survey answers, and predicted vs actual walk time. Invites are shown by a short
id prefix only; the report contains no locations and no texts people typed.
"""

import argparse
import statistics
import sys
from collections import Counter
from datetime import datetime

from _common import ROOT  # noqa: F401  (puts backend/ on sys.path)

from app.models.db import user_test_rows

QUESTIONS = {"would_have_gone_out": "Would you have gone out without the invite?",
             "fair": "Did the meeting point feel fair?", "use_again": "Would you use it again?"}


def minutes_between(events: dict, a: str, b: str) -> float | None:
    if a in events and b in events:
        return (datetime.fromisoformat(events[b]) - datetime.fromisoformat(events[a])).total_seconds() / 60
    return None


def med(xs: list[float]) -> str:
    return f"{statistics.median(xs):.1f}" if xs else "–"


def report(since: str, until: str | None) -> str:
    invites, feedback = user_test_rows(since)
    if until:
        invites = [r for r in invites if r["created_at"] < until]
        tokens = {r["token"] for r in invites}
        feedback = [f for f in feedback if f["token"] in tokens]
    lines = [f"# StrollCall user test: {since} to {until or 'now'}", "",
             f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by scripts/user_test_report.py.", ""]

    stages = ["created", "opened", "accepted", "planned", "confirmed"]
    counts = {s: sum(s in r["public"].get("events", {}) for r in invites) for s in stages}
    counts["created"] = len(invites)
    lines += ["## Funnel", "", "| Stage | Invites |", "|---|---|"]
    lines += [f"| {s} | {counts[s]} |" for s in stages]
    outcomes = Counter((r["data"].get("error") or r["status"]) for r in invites)
    lines += ["", "Final status: " + ", ".join(f"{k} {v}" for k, v in sorted(outcomes.items())), ""]

    to_open = [m for r in invites if (m := minutes_between(r["public"].get("events", {}), "created", "opened")) is not None]
    to_accept = [m for r in invites if (m := minutes_between(r["public"].get("events", {}), "created", "accepted")) is not None]
    planning = [r["public"]["progress"]["seconds"]["done"] for r in invites
                if (r["public"].get("progress") or {}).get("seconds", {}).get("done") is not None]
    lines += ["## Timing", "", "| Measure | Median | n |", "|---|---|---|",
              f"| Invite created -> B opened the link (min) | {med(to_open)} | {len(to_open)} |",
              f"| Invite created -> B accepted (min) | {med(to_accept)} | {len(to_accept)} |",
              f"| B accepted -> plan ready (s) | {med(planning)} | {len(planning)} |", ""]

    lines += ["## After-walk survey", "", f"{len(feedback)} answers (all given with consent), "
              f"from {len({f['token'] for f in feedback})} invites.", "",
              "| Question | Yes | No | Not sure |", "|---|---|---|---|"]
    for k, q in QUESTIONS.items():
        c = Counter(f["data"].get(k) for f in feedback)
        lines.append(f"| {q} | {c['yes']} | {c['no']} | {c['not_sure']} |")

    pairs = [(f["data"]["predicted_walk_min"], f["data"]["actual_walk_min"]) for f in feedback
             if f["data"].get("actual_walk_min") is not None]
    lines += ["", "## Predicted vs actual walk time", "",
              "Predicted: the person's own leg plus the shared leg of the confirmed plan, at 80 m/min. "
              "Actual: what they reported, door to destination (optional question).", ""]
    if pairs:
        diffs = [act - pred for pred, act in pairs]
        lines += ["| Invite | Role | Predicted (min) | Actual (min) | Actual - predicted |", "|---|---|---|---|---|"]
        for f in feedback:
            d = f["data"]
            if d.get("actual_walk_min") is not None:
                lines.append(f"| {f['token'][:6]} | {f['role'].upper()} | {d['predicted_walk_min']:.1f} | "
                             f"{d['actual_walk_min']} | {d['actual_walk_min'] - d['predicted_walk_min']:+.1f} |")
        lines += ["", f"n = {len(pairs)}; median difference {statistics.median(diffs):+.1f} min, "
                  f"median absolute difference {statistics.median(abs(x) for x in diffs):.1f} min."]
    else:
        lines.append("No actual walk times reported yet.")
    lines += ["", "Small sample: these are a handful of friends, not a study. Self-reported times are approximate."]
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since", required=True, help="ISO date or time, e.g. 2026-11-02")
    p.add_argument("--until", help="ISO date or time (exclusive)")
    p.add_argument("--out")
    args = p.parse_args()
    text = report(args.since, args.until)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
