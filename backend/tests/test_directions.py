"""Turn instructions from a path's nodes, their street names and the drawn line."""

from app.services.directions import edge_streets, turn_steps

M = 1 / 111_320  # degrees of latitude per meter


def line(*legs):
    """A path from (0,0) built of (dnorth_m, deast_m) moves, one node every 50 m."""
    lat, lon, pts = 40.75, -73.98, [(40.75, -73.98)]
    for dn, de in legs:
        n = max(1, int(max(abs(dn), abs(de)) / 50))
        for _ in range(n):
            lat += dn / n * M
            lon += de / n * M / 0.758  # cos(40.75)
            pts.append((lat, lon))
    return pts


def test_left_turn_onto_a_cross_street_and_corner_preference():
    pts = line((200, 0), (0, -150))  # north 200 m, then west 150 m
    names = [{"5th Ave"}] * 4 + [{"5th Ave", "E 20th St"}] + [{"E 20th St"}] * 3
    steps = turn_steps(pts, list(range(len(pts))), names)
    assert [s["text"] for s in steps] == ["Head north on 5th Ave", "Turn left onto E 20th St"]
    assert abs(steps[1]["along_m"] - 200) < 5


def at(*meters):
    """Points at (north_m, east_m) offsets."""
    return [(40.75 + n * M, -73.98 + e * M / 0.758) for n, e in meters]


def test_crosswalks_fold_into_the_street_and_paths_are_named_as_paths():
    # North on Broadway; a 20 m crossing next to Spring St; on up Broadway; then right onto a park path.
    pts = at((0, 0), (100, 0), (110, 0), (120, 0), (220, 0), (220, 60), (220, 120))
    names = [{"Broadway"}, {"Broadway", "Spring St"}, {"Spring St"}, {"Broadway", "Spring St"}, {"Broadway"},
             set(), set()]
    steps = turn_steps(pts, list(range(len(pts))), names)
    assert [s["text"] for s in steps] == ["Head north on Broadway", "Turn right onto the path"]
    assert abs(steps[1]["along_m"] - 220) < 3


def test_edge_streets_prefers_the_current_street_at_corners():
    names = [{"A St"}, {"A St", "B Ave"}, {"A St", "B Ave"}, {"B Ave"}]
    assert edge_streets(names) == ["A St", "A St", "B Ave"]
