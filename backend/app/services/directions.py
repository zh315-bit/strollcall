"""Turn-by-turn steps ("Turn left onto E 81st St") from a path on the local walking graph.

Street names come from the graph build (drive streets within 20 m of each walk node, since NYC
sidewalks are unnamed footways). An edge is on a street when both its ends are near it; when
several streets qualify (corners), the one we are already on wins, then the one the next edge
shares. Short pieces (crosswalks, a corner) fold into the street around them, so a step is a real
change of street. Turns come from the bearing 20 m before and after each change. Nothing here is
more precise than the map: distances are along the drawn line.
"""

import math

from app.core.geo import haversine_m

Point = tuple[float, float]
MIN_SEGMENT_M = 30.0  # shorter changes of street are folded into their neighbours
BEARING_SPAN_M = 20.0
COMPASS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]


def bearing(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def _point_at(geometry: list[Point], cum: list[float], target: float) -> Point:
    """The point `target` meters along the line (clamped to its ends)."""
    target = min(max(target, 0.0), cum[-1])
    for i in range(1, len(geometry)):
        if cum[i] >= target:
            seg = cum[i] - cum[i - 1]
            t = (target - cum[i - 1]) / seg if seg else 0.0
            a, b = geometry[i - 1], geometry[i]
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return geometry[-1]


def edge_streets(node_names: list[set[str]]) -> list[str | None]:
    """One street name (or None: a path, a plaza) per edge between consecutive path nodes."""
    common = [node_names[k] & node_names[k + 1] for k in range(len(node_names) - 1)]
    out: list[str | None] = []
    for k, names in enumerate(common):
        prev = out[-1] if out else None
        if not names:
            out.append(None)
        elif prev in names:
            out.append(prev)
        else:
            nxt = common[k + 1] if k + 1 < len(common) else set()
            out.append(sorted(names & nxt)[0] if names & nxt else sorted(names)[0])
    return out


def _segments(streets: list[str | None], node_along: list[float]) -> list[dict]:
    segs: list[dict] = []
    for k, name in enumerate(streets):
        if segs and segs[-1]["street"] == name:
            segs[-1]["end"] = node_along[k + 1]
        else:
            segs.append({"street": name, "start": node_along[k], "end": node_along[k + 1]})
    # Fold short pieces into the street before them (or after, at the start), then re-merge.
    changed = True
    while changed and len(segs) > 1:
        changed = False
        for i, s in enumerate(segs):
            if s["end"] - s["start"] < MIN_SEGMENT_M:
                if i > 0:
                    segs[i - 1]["end"] = s["end"]
                else:
                    segs[1]["start"] = s["start"]
                del segs[i]
                changed = True
                break
        merged = []
        for s in segs:
            if merged and merged[-1]["street"] == s["street"]:
                merged[-1]["end"] = s["end"]
            else:
                merged.append(s)
        segs = merged
    return segs


def _turn(angle: float) -> tuple[str, str]:
    """(kind, verb) for a change of heading in degrees (-180..180, right positive)."""
    a = abs(angle)
    side = "right" if angle > 0 else "left"
    if a < 25:
        return "straight", "Continue"
    if a < 60:
        return f"slight_{side}", f"Bear {side}"
    if a < 150:
        return side, f"Turn {side}"
    return "uturn", "Turn around"


def turn_steps(geometry: list[Point], node_geo_index: list[int], node_names: list[set[str]]) -> list[dict]:
    """Steps for a leg. geometry is the drawn line; node_geo_index[k] is where path node k sits in
    it; node_names[k] are its nearby streets. Each step: text, kind, street, along_m (where the
    manoeuvre happens), lat, lon."""
    if len(geometry) < 2 or len(node_geo_index) < 2:
        return []
    cum = [0.0]
    for i in range(1, len(geometry)):
        cum.append(cum[-1] + haversine_m(*geometry[i - 1], *geometry[i]))
    node_along = [cum[i] for i in node_geo_index]
    node_along[0], node_along[-1] = 0.0, cum[-1]  # the snap walks belong to the first/last street
    segs = _segments(edge_streets(node_names), node_along)

    first = segs[0]
    # Heading along the middle half of the first street: the start often crosses onto it first.
    span = first["end"] - first["start"]
    a, b = _point_at(geometry, cum, span / 4), _point_at(geometry, cum, 3 * span / 4)
    head = COMPASS[round(bearing(a, b) / 45) % 8]
    steps = [{"text": f"Head {head}" + (f" on {first['street']}" if first["street"] else ""),
              "kind": "depart", "street": first["street"], "along_m": 0.0,
              "lat": geometry[0][0], "lon": geometry[0][1]}]
    for s in segs[1:]:
        at = s["start"]
        here = _point_at(geometry, cum, at)
        before = bearing(_point_at(geometry, cum, at - BEARING_SPAN_M), here)
        after = bearing(here, _point_at(geometry, cum, at + BEARING_SPAN_M))
        kind, verb = _turn((after - before + 540) % 360 - 180)
        where = f"onto {s['street']}" if s["street"] else "onto the path"
        if kind == "straight" and not s["street"]:
            text = "Continue on the path"
        else:
            text = f"{verb} {where}"
        steps.append({"text": text, "kind": kind, "street": s["street"], "along_m": round(at, 1),
                      "lat": here[0], "lon": here[1]})
    return steps
