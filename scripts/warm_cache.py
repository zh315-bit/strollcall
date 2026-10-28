"""Pre-fetch Overpass tiles for the demo neighborhoods into the disk cache before a demo.

    python scripts/warm_cache.py                    # cache/ (7 days), used by the app
    python scripts/warm_cache.py --dir fixtures     # fixtures/, replayed by USE_MOCKS=true

Every meetup and destination tile (~1.1 x 1.1 km) inside DEMO_AREAS is fetched, 2 x 2 tiles
per Overpass query, one query at a time with a pause, as the Overpass usage policy asks.
Afterwards any pair of origins inside these areas is planned from cache. Each batch gets
up to 3 attempts; tiles already cached are skipped, so a rerun only fetches what failed.
"""

import argparse
import time
from pathlib import Path

from _common import ROOT

from app.core.config import get_settings
from app.core.errors import ProviderError
from app.providers.overpass import KINDS, OverpassProvider, batches, tiles_in_box

# (south, west, north, east): Lower Manhattan, about Chambers St to 34th St, Hudson River to the East River.
# Covers the six benchmark pairs plus the planner's search radius around them.
DEMO_AREAS = {
    "Village / SoHo / Union Square / Flatiron": (40.705, -74.020, 40.758, -73.966),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=None, help="cache root (default: CACHE_DIR, i.e. cache/)")
    args = parser.parse_args()
    update = {"overpass_timeout_s": 60.0}
    if args.dir:
        update["cache_dir"] = (ROOT / args.dir) if not Path(args.dir).is_absolute() else Path(args.dir)
    overpass = OverpassProvider(settings=get_settings().model_copy(update=update))

    failed = 0
    for area, box in DEMO_AREAS.items():
        tiles = tiles_in_box(*box)
        for kind in KINDS:
            todo = overpass.missing_tiles(kind, tiles)
            print(f"{area} / {kind}: {len(tiles)} tiles, {len(todo)} to fetch")
            for batch in batches(todo):
                for attempt in range(3):
                    started = time.monotonic()
                    try:
                        places = overpass.fetch_tiles(kind, batch)
                        n = sum(len(p) for p in places.values())
                        print(f"  ok    {len(batch)} tiles, {n} places ({time.monotonic() - started:.0f} s)")
                        break
                    except ProviderError as e:
                        print(f"  fail  {len(batch)} tiles: {e.message}")
                        if attempt < 2:
                            time.sleep(30 * (attempt + 1))
                else:
                    failed += 1
                time.sleep(2)
    print("done" if not failed else f"{failed} batches failed; rerun to fetch only those")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
