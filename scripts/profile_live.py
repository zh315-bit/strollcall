"""Time the invite flow on a deployed server, end to end, as a page sees it.

    python scripts/profile_live.py --base https://strollcall.onrender.com --runs 3 --out FILE.json

Uses only the public benchmark points in fixtures/nyc_origins.json (never a real person's
location). Each run: create an invite (A's text and preferences), accept it (B's text), poll
every 0.5 s until planning finishes. Records the request latencies, the time until the plan is
visible, the server's own progress seconds and stage timings (if the server reports them),
and /health's database round trip. A first /health wakes a sleeping free-plan service; its time
is reported separately as the cold start.
"""

import argparse
import json
import statistics
import sys
import time

import httpx
from _common import load_cases

A_TEXT = "25 minutes, quiet streets, coffee at the end"
B_TEXT = "somewhere green on the way would be nice"


def run_once(client: httpx.Client, case: dict) -> dict:
    a, b = case["a"], case["b"]
    t0 = time.perf_counter()
    r = client.post("/api/invites", json={"a_intent": case["intent"].model_dump(), "a_text": A_TEXT,
                                          "a_origin": {"lat": a[0], "lon": a[1]}})
    r.raise_for_status()
    created = time.perf_counter() - t0
    token, a_key = r.json()["token"], r.json()["a_key"]
    t1 = time.perf_counter()
    client.post(f"/api/invites/{token}/accept",
                json={"b_origin": {"lat": b[0], "lon": b[1]}, "b_text": B_TEXT}).raise_for_status()
    accepted = time.perf_counter() - t1
    polls, view = 0, {}
    while time.perf_counter() - t1 < 120:
        view = client.get(f"/api/invites/{token}", headers={"X-Invite-Key": a_key}).json()
        polls += 1
        if view["status"] != "planning":
            break
        time.sleep(0.5)
    progress = view.get("progress") or {}
    return {"case": case["id"], "status": view.get("status"), "create_s": round(created, 2),
            "accept_s": round(accepted, 2), "plan_visible_s": round(time.perf_counter() - t1, 2),
            "polls": polls, "server_seconds": progress.get("seconds"), "stage_timings": progress.get("timings"),
            "sources": view.get("sources")}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="https://strollcall.onrender.com")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--case", default="p1")
    p.add_argument("--out")
    args = p.parse_args()
    case = next(c for c in load_cases() if c["id"] == args.case)
    with httpx.Client(base_url=args.base, timeout=90) as client:
        t = time.perf_counter()
        health = client.get("/health").json()
        cold = round(time.perf_counter() - t, 2)
        runs = [run_once(client, case) for _ in range(args.runs)]
        db = client.get("/health").json().get("database")
    out = {"base": args.base, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "first_health_s": cold, "database": db, "meta": health.get("providers", {}).get("meta"),
           "runs": runs,
           "median_plan_visible_s": statistics.median(r["plan_visible_s"] for r in runs),
           "median_create_s": statistics.median(r["create_s"] for r in runs)}
    text = json.dumps(out, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
