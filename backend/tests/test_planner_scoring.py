from datetime import datetime

from app.models.schemas import Place, RouteLeg, TravelMatrix, WalkIntent
from app.services import planner

A, B = (40.7300, -74.0000), (40.7300, -73.9800)
WED_15 = datetime(2026, 10, 28, 15, 0)
W = planner.Weights(fit=1.0, gap=0.8, time_dev=0.6, detour=0.4, uncertainty=0.3)


def place(pid, lat=40.73, lon=-73.99, category="park", hours=None, **tags):
    return Place(id=pid, name=pid, lat=lat, lon=lon, category=category, opening_hours=hours, tags=tags)


def option(pid, t_a, t_b, d=700.0):
    return planner.MeetupOption(place(pid), t_a, t_b, d, d)


def candidate_set(meetups, destinations, shared):
    return planner.CandidateSet(meetups, destinations, TravelMatrix(
        durations_min=shared, distances_m=[[1000.0] * len(destinations) for _ in meetups]))


def test_elapsed_budget_and_closed_destination_filtered():
    cs = candidate_set(
        [option("m1", 9, 10)],
        [place("ok", category="cafe"), place("long", category="cafe"),
         place("closed", category="cafe", hours="Mo-Fr 08:00-09:00"), place("noroute", category="cafe")],
        [[15.0, 19.0, 15.0, None]],
    )
    ranked = planner.score_options(A, B, cs, WalkIntent(duration_min=25), W, WED_15)
    assert [o.destination.id for o in ranked] == ["ok"]  # elapsed 25 <= 28; long is 29
    assert cs.stats == {"elapsed_over_budget": 1, "destination_known_closed": 1, "shared_no_route": 1}


def test_must_be_open_requires_known_hours():
    cs = candidate_set([option("m1", 9, 10)],
                       [place("unknown", category="cafe"), place("open", category="cafe", hours="24/7")],
                       [[12.0, 12.0]])
    intent = WalkIntent(duration_min=25, hard_constraints=["must be open now"])
    ranked = planner.score_options(A, B, cs, intent, W, WED_15)
    assert [o.destination.id for o in ranked] == ["open"]
    assert cs.stats == {"open_status_unconfirmed": 1}


def test_fit_uses_type_and_vibes():
    cafe, park = place("c", category="cafe"), place("p", category="park")
    intent = WalkIntent(duration_min=25, endpoint_type="cafe", vibes=["green", "unknown vibe"])
    assert planner.fit_term(park, cafe, intent) == 1.0  # cafe matches, green via park meetup
    assert planner.fit_term(place("x", category="plaza"), cafe, intent) == 0.5
    assert planner.fit_term(park, cafe, WalkIntent(duration_min=25)) == 0.5  # nothing to check


def test_terms_normalized_and_smaller_gap_wins():
    cs = candidate_set([option("m1", 10, 10), option("m2", 8, 12)],
                       [place("e", category="cafe")], [[14.0], [14.0]])
    ranked = planner.score_options(A, B, cs, WalkIntent(duration_min=25), W, WED_15)
    assert [o.meetup.place.id for o in ranked] == ["m1", "m2"]
    for o in ranked:
        assert all(0.0 <= v <= 1.0 for v in o.terms.values())


def test_rank_is_deterministic_on_ties():
    cs = candidate_set([option("m2", 10, 10), option("m1", 10, 10)],
                       [place("e2", category="cafe"), place("e1", category="cafe")],
                       [[14.0, 14.0], [14.0, 14.0]])
    ranked = planner.score_options(A, B, cs, WalkIntent(duration_min=25), W, WED_15)
    order = [(o.meetup.place.id, o.destination.id) for o in ranked]
    assert order == [("m1", "e1"), ("m1", "e2"), ("m2", "e1"), ("m2", "e2")]
    assert [(o.meetup.place.id, o.destination.id) for o in planner.rank(list(reversed(ranked)))] == order


class LegORS:
    """Directions keyed by destination point; returns straight two-point legs of given minutes."""

    def __init__(self, minutes):
        self.minutes = minutes
        self.calls = 0

    def walk(self, start, end):
        self.calls += 1
        t = self.minutes[(start, end)]
        return RouteLeg(geometry=[start, end], distance_m=t * 80, duration_min=t)


def test_top_candidates_recheck_with_directions():
    m1, m2 = place("m1", 40.731, -73.99), place("m2", 40.732, -73.99)
    e = place("e", 40.735, -73.99, "cafe")
    opts = [
        planner.ScoredOption(planner.MeetupOption(m1, 9, 10, 1, 1), e, 14, 1, {"uncertainty": 1.0}, 0.5),
        planner.ScoredOption(planner.MeetupOption(m2, 9, 10, 1, 1), e, 14, 1, {"uncertainty": 1.0}, 0.4),
    ]
    p = lambda x: (x.lat, x.lon)
    ors = LegORS({
        (A, p(m1)): 9, (B, p(m1)): 16, (p(m1), p(e)): 14,  # directions disagree: gap 7
        (A, p(m2)): 9, (B, p(m2)): 10, (p(m2), p(e)): 14,
    })
    stats = {}
    top = planner.top_candidates(A, B, opts, WalkIntent(duration_min=25), ors, stats)
    assert [c.meeting_place_id for c in top] == ["m2"]
    assert stats == {"directions_broke_constraint": 1}
    assert top[0].total_elapsed_min == 24 and top[0].arrival_gap_min == 1
    assert "m2" in top[0].rationale and "unknown" in top[0].rationale


def test_joint_fit_weighs_both_people():
    from app.models.schemas import JointPreference

    joint = JointPreference(shared_vibes=["quiet"], a_priorities=["ends at a cafe"],
                            b_priorities=["green", "avoid traffic"], compromises=[])
    park_meet, plaza_meet = place("p", category="park"), place("q", category="plaza")
    cafe, books = place("c", category="cafe"), place("b", category="bookstore")
    intent = WalkIntent(duration_min=25)
    # park meetup + cafe: quiet (park) yes, A's cafe yes, B's green yes -> 1.0
    assert planner.fit_term(park_meet, cafe, intent, joint) == 1.0
    # plaza + cafe: quiet no (0.5*0), A yes (0.25), B green no -> 0.25
    assert planner.fit_term(plaza_meet, cafe, intent, joint) == 0.25
    # plaza + bookstore: quiet yes via bookstore (0.5), A no, B no -> 0.5
    assert planner.fit_term(plaza_meet, books, intent, joint) == 0.5


def test_unmeasurable_preferences_fall_back_to_intent_fit():
    from app.models.schemas import JointPreference

    joint = JointPreference(shared_vibes=[], a_priorities=["avoid traffic"], b_priorities=["chatty"],
                            compromises=[])
    assert planner.fit_term(place("m"), place("c", category="cafe"),
                            WalkIntent(duration_min=25, endpoint_type="cafe"), joint) == 1.0


def test_conflicting_types_both_represented_in_destinations():
    meetups = [planner.MeetupOption(place("m", 40.7300, -73.9900), 8, 9, 600, 700)]
    cafes = [place(f"cafe{i}", 40.7350 + i * 0.0001, -73.99, "cafe") for i in range(6)]
    parks = [place("park0", 40.7400, -73.99, "park")]  # farther than every cafe
    chosen = planner.select_destinations(cafes + parks, meetups, 9.0, WED_15, 4, {}, ["cafe", "park"])
    assert "park0" in [p.id for p in chosen] and len(chosen) == 4


def test_split_categories_only_for_different_wishes():
    cafe = WalkIntent(duration_min=30, endpoint_type="cafe")
    park = WalkIntent(duration_min=30, endpoint_type="park")
    green = WalkIntent(duration_min=30, vibes=["green"])
    assert planner.split_categories({"A": cafe, "B": park}) == ["park", "park_gate"]
    assert planner.split_categories({"A": cafe, "B": green}) == ["park", "park_gate"]  # green meetup for B
    assert planner.split_categories({"A": green, "B": WalkIntent(duration_min=30)}) == []  # nobody wants an ending
    assert planner.split_categories({"A": cafe, "B": cafe}) == []


def test_served_says_who_each_part_is_for():
    people = {"A": WalkIntent(duration_min=30, endpoint_type="cafe"),
              "B": WalkIntent(duration_min=30, endpoint_type="park", vibes=["green"])}
    who = planner.served(place("g", category="park_gate"), place("c", category="cafe"), people)
    assert who == {"meetup": ["B: park", "B: green"], "destination": ["A: cafe"]}
    assert planner._for_text(who["meetup"]) == "for B (park, green)"


def test_reserved_split_meetup_survives_the_gap_filter():
    points = [place(f"x{i}", category="plaza") for i in range(10)] + [place("gate", category="park_gate")]
    times = TravelMatrix(durations_min=[[9] * 10 + [8], [9] * 10 + [11]], distances_m=[[1] * 11, [1] * 11])
    kept = planner.filter_meetups(points, times, 30, {})
    assert "gate" not in [o.place.id for o in kept]  # gap 3 loses to ten gap-0 plazas
    kept = planner.filter_meetups(points, times, 30, {}, reserve=["park", "park_gate"])
    assert "gate" in [o.place.id for o in kept]


def test_split_destinations_fit_the_time_left_after_the_split_meetup():
    gate = planner.MeetupOption(place("gate", 40.7300, -73.9900, "park_gate"), 10, 12, 800, 900)
    near_cafe = place("near", 40.7330, -73.9900, "cafe")  # ~330 m, ~5 min
    far_cafe = place("far", 40.7500, -73.9900, "cafe")  # ~2.2 km, too far for 21 min left
    added = planner.split_destinations([near_cafe, far_cafe], [gate], [], ["park", "park_gate"],
                                       ["cafe", "park"], WalkIntent(duration_min=30), WED_15, {})
    assert [p.id for p in added] == ["near"]
