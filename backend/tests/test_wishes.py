from datetime import datetime

import pytest

from app.models.schemas import JointPreference, Place, TravelMatrix, WalkIntent
from app.services import planner
from app.services.wishes import (
    Wish, Wishes, interpret_wishes, keyword_wishes, requirement_score, requirement_status,
)

A_TEXT = "Coffee at the end, ideally somewhere we can sit outside since it's sunny"
B_TEXT = "Somewhere I can get some work done on my laptop afterwards; I don't eat animal products"


def place(pid, category="cafe", lat=40.735, lon=-73.99, **tags):
    return Place(id=pid, name=pid, lat=lat, lon=lon, category=category, tags=tags)


class FakeMeta:
    name = "meta"

    def __init__(self, result):
        self.result = result

    def structured_json(self, system, user, schema, name="result"):
        return self.result


@pytest.fixture
def use_meta(monkeypatch):
    def install(result):
        monkeypatch.setattr("app.providers.get_meta", lambda: FakeMeta(result))
    return install


def test_meta_wishes_keep_only_quotes_from_the_text(use_meta):
    use_meta({"wishes": [
        {"requirement": "outdoor_seating", "who": "A", "quote": "sit outside"},
        {"requirement": "wifi", "who": "B", "quote": "work done on my laptop"},
        {"requirement": "vegan_options", "who": "B", "quote": "I don't eat animal products"},
        {"requirement": "wheelchair_access", "who": "B", "quote": "I use a wheelchair"},  # not said
        {"requirement": "wifi", "who": "A", "quote": "work done on my laptop"},  # B's words, not A's
    ]})
    w = interpret_wishes(A_TEXT, B_TEXT)
    assert w.source == "meta" and w.note == "dropped 2"
    assert {(x.who, x.requirement) for x in w.items} == {("A", "outdoor_seating"), ("B", "wifi"), ("B", "vegan_options")}


def test_mock_wish_without_matching_text_is_dropped():
    w = interpret_wishes("just coffee", "green please")
    assert w.source == "mock" and w.items == []


def test_keyword_baseline_misses_implied_wishes():
    w = keyword_wishes(A_TEXT, B_TEXT)
    keys = {(x.who, x.requirement) for x in w.items}
    assert ("A", "outdoor_seating") in keys
    assert ("B", "wifi") not in keys and ("B", "vegan_options") not in keys  # laptop, animal products


def test_requirement_status_yes_no_unknown():
    wish = Wish(requirement="outdoor_seating", who="A", quote="sit outside")
    meet = place("m", "plaza")
    assert requirement_status(wish, meet, place("c", outdoor_seating="yes")) is True
    assert requirement_status(wish, meet, place("c", outdoor_seating="no")) is False
    assert requirement_status(wish, meet, place("c")) is None
    assert requirement_score(wish, meet, place("c")) == pytest.approx(0.3)
    chain = Wish(requirement="not_a_chain", who="B", quote="not another Starbucks")
    assert requirement_status(chain, meet, place("s", brand="Starbucks")) is False
    assert requirement_status(chain, meet, place("i")) is True


def test_wishes_change_the_pick_between_equal_cafes():
    wishes = Wishes(items=[Wish(requirement="wifi", who="B", quote="laptop")], source="meta")
    m = planner.MeetupOption(place("m", "plaza", 40.73, -73.99), 9, 9, 700, 700)
    plain, wifi = place("cafe-a"), place("cafe-b", internet_access="wlan")
    cs = planner.CandidateSet([m], [plain, wifi], TravelMatrix(durations_min=[[14.0, 14.0]],
                                                                distances_m=[[1000.0, 1000.0]]))
    w = planner.Weights(1.0, 0.8, 0.6, 0.4, 0.3, 0.1)
    args = ((40.73, -74.0), (40.73, -73.98), cs, WalkIntent(duration_min=25), w, datetime(2026, 10, 31, 15))
    assert planner.score_options(*args)[0].destination.id == "cafe-a"  # tie: id order
    joint = JointPreference(shared_vibes=[], a_priorities=[], b_priorities=[], compromises=[])
    assert planner.score_options(*args, joint, wishes)[0].destination.id == "cafe-b"


def test_shortlist_prefers_places_that_meet_wishes():
    wishes = Wishes(items=[Wish(requirement="outdoor_seating", who="A", quote="outside")], source="meta")
    meetups = [planner.MeetupOption(place("m", "plaza", 40.7300, -73.99), 8, 9, 600, 700)]
    near = [place(f"c{i}", lat=40.7350 + i * 0.00005) for i in range(5)]
    patio = place("patio", lat=40.7362, outdoor_seating="yes")  # ~1.5 min further, within the window
    chosen = planner.select_destinations(near + [patio], meetups, 9.0, datetime(2026, 10, 31, 15), 4, {},
                                         None, wishes)
    assert chosen[0].id == "patio"
