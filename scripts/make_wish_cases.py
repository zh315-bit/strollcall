"""Generate the pre-registered wish cases (fixtures/wish_cases.json). Run once, commit, then run
scripts/ablation.py --wish-cases. The rule below uses only the place data, never planner results.

    python scripts/make_wish_cases.py

Rule (fixed before any wish-case ablation run):
- Origins: public places in the snapshot (named subway entrances and parks), sampled with a fixed
  seed; A and B 1.2-2.0 km apart in a straight line, and the direct A-B walk on the local graph at
  most 1.2 x 30 = 36 min (the benchmark's "not infeasible by distance" rule; excludes river crossings).
- For each requirement with OSM data (outdoor seating, not a chain, wifi, wheelchair access, vegan
  options): keep a pair only if, within 900 m of its midpoint, at least 1 cafe has the tag value that
  meets it and at least 2 cafes do not (so the choice matters). Two cases per requirement.
- Texts: one plainer and one implied phrasing per requirement; the wish alternates between A and B;
  the other person writes a neutral line. Both want about 30 minutes; A wants to end at a cafe.
- Reference wish: exactly the requirement the case was generated for.
"""

import gzip
import json
import math
import random

from _common import ROOT

from app.core.config import get_settings
from app.core.geo import haversine_m
from app.models.schemas import Place
from app.providers.local_routing import LocalRouting, OutsideCoverage, load_graph
from app.services.wishes import REQUIREMENTS

SEED = 20261028
RADIUS_M = 900
MIN_M, MAX_M = 1200, 2000
PER_REQUIREMENT = 2
NEUTRAL = "Somewhere nice, about 30 minutes"
PHRASES = {
    "outdoor_seating": ["It's warm out, let's get a coffee we can drink sitting outside",
                        "A coffee on a patio in the sun would be perfect"],
    "not_a_chain": ["Some little local place please, not a big chain",
                    "Anywhere for coffee as long as it's not Starbucks"],
    "wifi": ["I need to answer a few emails on my laptop afterwards",
             "I'll want to get online for a bit once we sit down"],
    "wheelchair_access": ["I use a wheelchair, so the cafe has to work for that",
                          "I'm in a wheelchair this month after my knee surgery"],
    "vegan_options": ["I'm plant-based, so somewhere with vegan options",
                      "I don't eat dairy, eggs or any other animal products"],
}


def main() -> int:
    s = get_settings()
    data = json.load(gzip.open(s.places_snapshot_path, "rt"))
    origins = [p for p in data["meetup"] if p["category"] in ("subway_entrance", "park")]
    cafes = [Place.model_validate(p) for p in data["destination"] if p["category"] == "cafe"]
    routing = LocalRouting(load_graph(s.graph_path))
    rng = random.Random(SEED)

    def walk_ok(a, b) -> bool:
        try:
            t = routing.matrix([(a["lat"], a["lon"])], [(b["lat"], b["lon"])]).durations_min[0][0]
        except OutsideCoverage:
            return False
        return t is not None and t <= 1.2 * 30
    rng.shuffle(origins)

    cases, used = [], set()
    for key, phrases in PHRASES.items():
        req = REQUIREMENTS[key]
        made = 0
        for i in range(len(origins)):
            if made == PER_REQUIREMENT:
                break
            a = origins[i]
            for b in origins[i + 1:i + 200]:
                d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
                if not (MIN_M <= d <= MAX_M) or a["id"] in used or b["id"] in used:
                    continue
                mid = ((a["lat"] + b["lat"]) / 2, (a["lon"] + b["lon"]) / 2)
                near = [c for c in cafes if haversine_m(*mid, c.lat, c.lon) <= RADIUS_M]
                meets = sum(req.check(c) is True for c in near)
                if meets >= 1 and len(near) - meets >= 2 and walk_ok(a, b):
                    who = "A" if made % 2 == 0 else "B"
                    text = phrases[made]
                    cases.append({
                        "id": f"w{len(cases) + 1}",
                        "requirement": key,
                        "a": {"name": a["name"], "osm_id": a["id"], "lat": a["lat"], "lon": a["lon"]},
                        "b": {"name": b["name"], "osm_id": b["id"], "lat": b["lat"], "lon": b["lon"]},
                        "intent": {"duration_min": 30, "endpoint_type": "cafe"},
                        "b_intent": {"duration_min": 30},
                        "a_text": text if who == "A" else "Coffee at the end, about 30 minutes",
                        "b_text": text if who == "B" else NEUTRAL,
                        "expected_wishes": [[who, key]],
                        "cafes_within_900m": {"meet": meets, "other": len(near) - meets},
                    })
                    used |= {a["id"], b["id"]}
                    made += 1
                    break
        print(f"{key}: {made} cases")

    out = {
        "_rule": __doc__.split("Rule (fixed before any wish-case ablation run):")[1].strip(),
        "seed": SEED,
        "depart_at": "2026-10-31T15:00:00-04:00",
        "cases": cases,
    }
    (ROOT / "fixtures" / "wish_cases.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote fixtures/wish_cases.json: {len(cases)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
