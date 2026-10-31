"""Warm the Muse Glimmer endpoint on Modal for a short window, then let it scale down.

    python scripts/glimmer_warm.py                    # warm, open a 15-min window on the live site
    python scripts/glimmer_warm.py --minutes 45       # e.g. the demo recording
    python scripts/glimmer_warm.py --no-site          # warm only (evaluation runs)

Run it about 4 minutes before creating an invite: a cold start takes about 3.3 minutes.
It prints the model, precision, host, GPU and the time it became ready (for the demo recording),
tells the live site to read wishes with Glimmer until the window ends, pings once a minute so
the container stays up, and closes the window on exit (Ctrl-C ends it early). Two minutes after
the last ping the endpoint scales to zero.

Budget: refuses to start when this month's Modal bill (`modal billing report`) plus the
window's estimate would pass $20 (the workspace limit in the Modal dashboard is $25).
Needs OPEN_WEIGHTS_API_KEY in .env and a logged-in Modal CLI. Never prints the token.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime

from _common import ROOT  # noqa: F401  (puts backend/ on the path)

import httpx

from app.core.config import get_settings

STOP_USD = 20.0
COLD_START_MIN = 3.3  # measured 2026-10-31: 199 s
SCALEDOWN_MIN = 2.0
PING_EVERY_S = 60
READY_DEADLINE_S = 10 * 60
SITE = "https://strollcall.onrender.com"


def month_spend() -> float | None:
    modal = shutil.which("modal") or str(ROOT / ".venv" / "bin" / "modal")
    try:
        out = subprocess.run([modal, "billing", "report", "--for", "this month", "--json"],
                             capture_output=True, text=True, timeout=60, check=True).stdout
        return sum(float(r["cost"]) for r in json.loads(out))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return None


def ping(client: httpx.Client, s) -> float:
    """One tiny completion; returns seconds taken. Raises on any failure."""
    t = time.monotonic()
    r = client.post(f"{s.open_weights_base_url}/chat/completions", json={
        "model": s.open_weights_model, "max_tokens": 4,
        "messages": [{"role": "system", "content": "Reasoning strength: low."},
                     {"role": "user", "content": "Reply with: ok"}]})
    r.raise_for_status()
    return time.monotonic() - t


def compile_grammar() -> str:
    """One wish read with the app's own schema (a made-up wish), so SGLang compiles the JSON grammar
    now (about 1.3 s, once per schema) and not on the first real wish."""
    from app.core.config import output_cap_override
    from app.providers.glimmer import GlimmerProvider
    from app.services.intent import INTENT_SCHEMA, SYSTEM_PROMPT

    output_cap_override.set(get_settings().parse_max_output_tokens)
    p = GlimmerProvider(timeout_s=30)
    try:
        p.structured_json(SYSTEM_PROMPT, "Walk description:\nA 30 minute walk to a cafe", INTENT_SCHEMA,
                          name="walk_intent")
    except Exception as e:  # noqa: BLE001 - reported, the window still opens
        return f"wish-reading check failed: {e}"
    return f"wish-reading check: valid JSON in {p.last_call['latency_s']:.2f} s, reasoning off"


def set_site_window(site: str, key: str, minutes: float) -> str:
    try:
        r = httpx.post(f"{site}/api/open-weights/window", json={"minutes": minutes},
                       headers={"Authorization": f"Bearer {key}"}, timeout=30)
    except httpx.HTTPError as e:
        return f"site unreachable ({type(e).__name__})"
    if r.status_code == 404:
        return "site has no OPEN_WEIGHTS_API_KEY yet: wishes there stay on the Meta API"
    if r.status_code != 200:
        return f"site answered HTTP {r.status_code}"
    body = r.json()
    if body["open"] and not body["enabled"]:
        return "window open, but TEXT_PROVIDER_PARSE is not open_weights on the site"
    return f"window open until {body['until'][11:19]} UTC" if body["open"] else "window closed"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--minutes", type=float, default=15, help="warm window length (default 15)")
    p.add_argument("--no-site", action="store_true", help="don't open a window on the live site")
    p.add_argument("--site", default=SITE)
    args = p.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # each line as it happens, also when recorded or piped
    s = get_settings()
    key = s.open_weights_api_key.get_secret_value()
    if not key:
        print("OPEN_WEIGHTS_API_KEY is not set in .env")
        return 1

    estimate = (COLD_START_MIN + args.minutes + SCALEDOWN_MIN) / 60 * s.open_weights_usd_per_hour
    spent = month_spend()
    if spent is None:
        print("Couldn't read the Modal billing report (is the Modal CLI logged in?); not starting.")
        return 1
    print(f"Modal this month: ${spent:.2f}. This window: up to ${estimate:.2f}. Stop at ${STOP_USD:.0f}.")
    if spent + estimate > STOP_USD:
        print("Over the $20 stop: not warming. Shorten --minutes or stop here.")
        return 1

    label = (f"Muse Glimmer 30B ({s.open_weights_repo}@{s.open_weights_revision[:7]}) · "
             f"{s.open_weights_precision} · Modal · 1x {s.open_weights_gpu} · endpoint {s.open_weights_deployment}")
    print(label)
    started = time.monotonic()
    print(f"{datetime.now():%H:%M:%S}  waking the endpoint (cold start is about 3 minutes)...")
    client = httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60)
    while True:
        try:
            took = ping(client, s)
            break
        except httpx.HTTPError as e:
            waited = time.monotonic() - started
            if waited > READY_DEADLINE_S:
                print(f"Not ready after {waited:.0f} s ({type(e).__name__}); giving up. It scales down on its own.")
                return 1
            time.sleep(5)
    ready = time.monotonic() - started
    print(f"{datetime.now():%H:%M:%S}  READY in {ready:.0f} s (last answer {took:.2f} s) - {label}")
    print(f"{datetime.now():%H:%M:%S}  {compile_grammar()}")

    if not args.no_site:
        print(f"{datetime.now():%H:%M:%S}  live site: {set_site_window(args.site, key, args.minutes)}")
    end = time.monotonic() + args.minutes * 60
    try:
        while time.monotonic() < end:
            time.sleep(min(PING_EVERY_S, max(0.0, end - time.monotonic())))
            if time.monotonic() >= end:
                break
            try:
                took = ping(client, s)
                left = (end - time.monotonic()) / 60
                print(f"{datetime.now():%H:%M:%S}  warm ({took:.2f} s), {left:.0f} min left")
            except httpx.HTTPError as e:
                print(f"{datetime.now():%H:%M:%S}  ping failed ({type(e).__name__}); trying again in a minute")
    except KeyboardInterrupt:
        print("\nEnding the window early.")
    if not args.no_site:
        print(f"{datetime.now():%H:%M:%S}  live site: {set_site_window(args.site, key, 0)}")
    print(f"{datetime.now():%H:%M:%S}  done; the endpoint scales to zero after {SCALEDOWN_MIN:.0f} idle minutes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
