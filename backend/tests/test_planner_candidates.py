from datetime import datetime

from app.models.schemas import Place, TravelMatrix, WalkIntent
from app.services import planner


def place(pid, lat, lon, category="park", hours=None):
    return Place(id=pid, name=pid, lat=lat, lon=lon, category=category, opening_hours=hours)


def test_select_meetup_points_dedupes_and_limits():
    mid = (40.7300, -73.9900)
    places = [
        place("far", 40.7400, -73.9900),
        place("near", 40.7301, -73.9900),
        place("near-dup", 40.7302, -73.9900),  # ~11 m from "near"
        place("mid", 40.7330, -73.9900),
    ]
    stats = {}
    chosen = planner.select_meetup_points(places, mid, 2, stats)
    assert [p.id for p in chosen] == ["near", "mid"]
    assert stats == {"meetup_duplicate_spot": 1, "meetup_beyond_query_limit": 1}


def test_filter_meetups_applies_time_share_gap_and_routes():
    points = [place(f"m{i}", 40.73, -73.99 + i * 0.001) for i in range(5)]
    times = TravelMatrix(
        durations_min=[[8, 10, 16, None, 6], [9, 3, 8, 7, 7]],
        distances_m=[[1] * 5, [1] * 5],
    )
    stats = {}
    kept = planner.filter_meetups(points, times, 25, stats)  # time share 15 min
    assert [o.place.id for o in kept] == ["m4", "m0"]  # equal gap: shorter t_max first
    assert stats == {"meetup_gap_over_max": 1, "meetup_over_time_share": 1, "meetup_no_route": 1}


def test_select_destinations_skips_closed_and_prefers_time_left():
    meetups = [planner.MeetupOption(place("m", 40.7300, -73.9900), 8, 9, 600, 700)]
    wed_10 = datetime(2026, 10, 28, 10, 0)
    places = [
        place("closed", 40.7350, -73.9900, "cafe", "Mo-Fr 12:00-18:00"),
        place("right", 40.7350, -73.9900, "cafe"),  # ~560 m, ~9 min
        place("too-near", 40.7302, -73.9900, "cafe"),
        place("m", 40.7300, -73.9900, "park"),
    ]
    stats = {}
    chosen = planner.select_destinations(places, meetups, 9.0, wed_10, 1, stats)
    assert [p.id for p in chosen] == ["right"]
    assert stats == {
        "destination_known_closed": 1, "destination_is_meetup_point": 1, "destination_beyond_limit": 1,
    }


def test_destination_types_follow_intent():
    assert planner.destination_types(WalkIntent(duration_min=25, endpoint_type="bakery")) == ["bakery"]
    assert "landmark" not in planner.destination_types(WalkIntent(duration_min=25))


def test_search_radius_bounds():
    assert planner.meetup_search_radius((40.73, -74.0), (40.7301, -74.0)) == 300
    assert planner.meetup_search_radius((40.70, -74.0), (40.80, -74.0)) == 1200
