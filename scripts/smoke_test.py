"""Live check of every external dependency with real keys (reads .env).

    python scripts/smoke_test.py                 # Muse Spark intent, Overpass, ORS
    python scripts/smoke_test.py --media --wav x.wav   # also Muse Image and Voice Transcribe

Uses only public places from fixtures/nyc_origins.json. Prints pass/fail per provider and
the Meta spend recorded by the spend guard.
"""

import argparse
import os
import sys
import traceback

os.environ["USE_MOCKS"] = "false"  # this script always talks to the real services

from _common import ROOT, load_origins, point

from app.core.budget import SpendGuard
from app.providers.meta import MetaProvider
from app.providers.ors import ORSProvider
from app.providers.overpass import OverpassProvider
from app.services.intent import parse_intent

INTENT_TEXT = "25 minutes, quiet streets, coffee at the end"


def check_intent() -> str:
    parsed = parse_intent(INTENT_TEXT)
    print(f"  {parsed.model_dump_json(indent=2)}")
    if parsed.source != "meta":
        raise RuntimeError(f"intent came from {parsed.source}, not Muse Spark ({parsed.note})")
    return f"duration {parsed.intent.duration_min} min, endpoint {parsed.intent.endpoint_type}"


def check_overpass(origins: dict) -> str:
    lat, lon = point(origins["smoke"]["center"])
    places = OverpassProvider().places_near(lat, lon, 500)
    for p in places[:5]:
        print(f"  {p.category:9} {p.name} (hours: {p.opening_hours or 'unknown'})")
    if not places:
        raise RuntimeError("no places returned")
    return f"{len(places)} places within 500 m of {origins['smoke']['center']['name']}"


def check_ors(origins: dict) -> str:
    start, end = point(origins["smoke"]["center"]), point(origins["smoke"]["route_to"])
    leg = ORSProvider().walk(start, end)
    if leg.duration_min <= 0 or len(leg.geometry) < 2:
        raise RuntimeError("empty leg")
    return (
        f"{origins['smoke']['center']['name']} -> {origins['smoke']['route_to']['name']}: "
        f"{leg.distance_m:.0f} m, {leg.duration_min:.1f} min, {len(leg.geometry)} points"
    )


def check_image() -> str:
    image = MetaProvider().generate_image(
        "A friendly flat illustration of two friends walking toward each other "
        "on a quiet tree-lined street, warm autumn light, no text"
    )
    out = ROOT / "data" / "smoke_invite.webp"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(image)
    return f"{len(image)} bytes -> {out.relative_to(ROOT)}"


def check_voice(wav_path: str) -> str:
    with open(wav_path, "rb") as f:
        text = MetaProvider().transcribe(f.read(), "audio/wav")
    if not text:
        raise RuntimeError("empty transcript")
    return repr(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--media", action="store_true", help="also call Muse Image (~$0.01)")
    parser.add_argument("--wav", help="mono 16-bit 16/24 kHz WAV for Muse Voice Transcribe")
    args = parser.parse_args()

    origins = load_origins()
    guard = SpendGuard()
    spend_before = guard.today_total()

    checks = [
        ("Muse Spark intent", check_intent),
        ("Overpass places", lambda: check_overpass(origins)),
        ("ORS walking leg", lambda: check_ors(origins)),
    ]
    if args.media:
        checks.append(("Muse Image", check_image))
    if args.wav:
        checks.append(("Muse Voice Transcribe", lambda: check_voice(args.wav)))

    results = []
    for name, fn in checks:
        print(f"\n== {name}")
        try:
            summary = fn()
            results.append((name, True, summary))
        except Exception as e:  # report every provider, then exit non-zero
            traceback.print_exc(limit=1)
            results.append((name, False, f"{type(e).__name__}: {e}"))

    print("\n== Summary")
    for name, ok, summary in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {summary}")
    spend_after = guard.today_total()
    print(
        f"\nMeta spend recorded by the guard: ${spend_after - spend_before:.6f} this run, "
        f"${spend_after:.6f} today of ${guard.daily_cap:.2f} cap"
    )
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
