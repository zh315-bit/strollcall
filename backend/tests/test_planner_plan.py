from datetime import datetime

import pytest

from app.core.errors import ProviderError
from app.models.schemas import Place, RouteLeg, TravelMatrix, WalkIntent
from app.services import planner

A, B = (40.7300, -74.0000), (40.7300, -73.9800)
WED_15 = datetime(2026, 10, 28, 15, 0)
MID = (40.7300, -73.9900)
W = planner.Weights(fit=1.0, gap=0.8, time_dev=0.6, detour=0.4, uncertainty=0.3)


def place(pid, lat, lon, category):
    return Place(id=pid, name=pid, lat=lat, lon=lon, category=category)


MEETUPS = [place(f"m{i}", 40.7300 + i * 0.001, -73.9900, "plaza") for i in range(3)]
DESTS = [place(f"e{i}", 40.7380 + i * 0.001, -73.9900, "cafe") for i in range(2)]


class FakeOverpass:
    def __init__(self, meetups=MEETUPS, dests=DESTS, error=None):
        self.meetups, self.dests, self.error = meetups, dests, error

    def meetup_candidates(self, lat, lon, radius):
        if self.error:
            raise self.error
        return self.meetups

    def destination_candidates(self, lat, lon, radius, types=None):
        return [d for d in self.dests if types is None or d.category in types]


class FakeORS:
    """Synthetic minutes: origin legs from `origin_times`, shared legs from `shared_times`."""

    def __init__(self, origin_times, shared_times, fail_directions=False):
        self.origin_times, self.shared_times = origin_times, shared_times
        self.fail_directions = fail_directions

    def matrix(self, sources, destinations):
        if sources == [A, B]:
            rows = [[self.origin_times[s][d] for d in destinations] for s in (A, B)]
        else:
            rows = [[self.shared_times.get((s, d)) for d in destinations] for s in sources]
        return TravelMatrix(durations_min=rows, distances_m=[[None if t is None else t * 80 for t in r] for r in rows])

    def walk(self, start, end):
        if self.fail_directions:
            raise ProviderError("routing_unavailable", "ORS directions HTTP 503")
        t = self.origin_times[start][end] if start in (A, B) else self.shared_times[(start, end)]
        return RouteLeg(geometry=[start, end], distance_m=t * 80, duration_min=t)


def pt(p):
    return (p.lat, p.lon)


def ors_with(origin, shared, **kw):
    return FakeORS(
        {A: {pt(m): origin[i][0] for i, m in enumerate(MEETUPS)},
         B: {pt(m): origin[i][1] for i, m in enumerate(MEETUPS)}},
        {(pt(m), pt(e)): shared for m in MEETUPS for e in DESTS},
        **kw,
    )


def test_feasible_plan_returns_three_ranked_candidates():
    ors = ors_with([(9, 10), (8, 11), (10, 10)], 14)
    result = planner.plan_walk(A, B, WalkIntent(duration_min=25), FakeOverpass(), ors, WED_15, W)
    assert result.status == "proposed"
    assert len(result.candidates) == 3
    assert result.candidates[0].meeting_place_id == "m2"  # gap 0
    assert set(result.places) >= {"m2", "e0"}
    for c in result.candidates:
        assert c.arrival_gap_min <= 5 and c.total_elapsed_min <= 28


def test_same_inputs_same_plan():
    def run():
        ors = ors_with([(9, 10), (9, 10), (9, 10)], 14)
        return planner.plan_walk(A, B, WalkIntent(duration_min=25), FakeOverpass(), ors, WED_15, W)
    assert run() == run()


def test_time_budget_failure_suggests_closer_destination():
    ors = ors_with([(9, 10), (8, 11), (10, 10)], 25)  # elapsed 35 > 28
    result = planner.plan_walk(A, B, WalkIntent(duration_min=25), FakeOverpass(), ors, WED_15, W)
    assert result.status == "no_feasible_plan" and result.candidates == []
    assert result.failure.constraint == "time_budget"
    assert result.failure.suggestion_type == "closer_destination"
    assert "35 minutes" in result.failure.suggestion


def test_gap_failure_suggests_longer_time():
    ors = ors_with([(3, 12), (2, 13), (4, 11)], 10)
    result = planner.plan_walk(A, B, WalkIntent(duration_min=25), FakeOverpass(), ors, WED_15, W)
    assert result.failure.constraint == "fair_gap"
    assert result.failure.suggestion_type == "longer_time"
    assert result.stats["meetup_gap_over_max"] == 3


def test_no_places_of_wanted_type():
    ors = ors_with([(9, 10), (8, 11), (10, 10)], 14)
    intent = WalkIntent(duration_min=25, endpoint_type="bookstore")
    result = planner.plan_walk(A, B, intent, FakeOverpass(), ors, WED_15, W)
    assert result.status == "no_feasible_plan"
    assert result.failure.constraint == "no_destination_places"
    assert result.failure.suggestion_type == "relaxed_preference"


def test_routing_failure_is_reported_not_drawn():
    ors = ors_with([(9, 10), (8, 11), (10, 10)], 14, fail_directions=True)
    result = planner.plan_walk(A, B, WalkIntent(duration_min=25), FakeOverpass(), ors, WED_15, W)
    assert result.status == "routing_unavailable" and result.candidates == []


def test_places_failure():
    overpass = FakeOverpass(error=ProviderError("places_unavailable", "Overpass unavailable"))
    result = planner.plan_walk(A, B, WalkIntent(duration_min=25), overpass, ors_with([(9, 10)] * 3, 14), WED_15, W)
    assert result.status == "places_unavailable"
