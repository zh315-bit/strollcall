""""Something else" typed under Pass by, Avoid and Stops on the way (services/custom_options.py):
the words become kinds and places from our own data, and what has no map data is said plainly."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import Place, RouteLeg
from app.providers.local_routing import AVOID_NEAR_M, LocalRouting
from app.services import custom_options
from app.services.custom_options import by_rules, understand

from .test_local_providers import LAT0, LON0, STEP, grid_graph

client = TestClient(app)

PLACES = [("times square", "way/1", "Times Square", 40.758, -73.9855, True),
          ("high line", "rel/2", "The High Line", 40.748, -74.0048, True),
          ("starbucks", "node/3", "Starbucks", 40.70, -74.00, False),
          ("starbucks", "node/4", "Starbucks", 40.75, -73.98, False)]


@pytest.fixture(autouse=True)
def our_places(monkeypatch):
    monkeypatch.setattr(custom_options, "_index", lambda: PLACES)
    custom_options._cache.clear()


@pytest.fixture
def model(monkeypatch):
    """The live model's answer, set per test; records what it was sent."""
    seen = {"answer": None, "sent": []}

    def fake(call):
        class M:
            def structured_json(self, system, user, schema, name="result"):
                seen["sent"].append(system + "\n" + user)
                return seen["answer"]
        return call(M()), "meta"

    monkeypatch.setattr("app.providers.meta_or_mock", fake)
    return seen


def test_rules_read_kinds_counts_and_what_has_no_data():
    assert by_rules("pass", "bridges and a nice view")["kinds"] == ["bridges", "viewpoints"]
    stops = by_rules("stops", "two coffees")
    assert stops["kinds"] == ["cafes"] and stops["count"] == 2
    assert by_rules("stops", "a bookstore and gelato")["kinds"] == ["bookstores", "ice_cream"]
    assert by_rules("avoid", "steps, traffic")["kinds"] == ["stairs", "busy_avenues"]
    assert by_rules("avoid", "hills")["unsupported"] == ["hills"]


def test_rules_take_a_name_we_have_as_a_place():
    r = by_rules("avoid", "Times Square, hills")
    assert r["places"] == ["Times Square"] and r["kinds"] == [] and r["unsupported"] == ["hills"]
    assert by_rules("pass", "the High Line")["places"] == ["High Line"]


def test_without_the_model_the_rules_answer(monkeypatch):
    def broken(call):
        from app.core.errors import ProviderError
        raise ProviderError("model_unavailable", "down")

    monkeypatch.setattr("app.providers.meta_or_mock", broken)
    u = understand("avoid", "Times Square and hills")
    assert u.source == "rules" and u.places == [{"id": "way/1", "name": "Times Square"}]
    assert u.note == "No map data for hills, so the route can't plan for it."


def test_the_model_only_picks_from_the_list_and_places_come_from_our_data(model):
    model["answer"] = {"kinds": ["bridges", "stairs", "lava"], "places": ["Times Square", "Atlantis"], "count": None,
                       "unsupported": ["shade"]}
    u = understand("pass", "a bridge, Times Square, Atlantis, some shade")
    assert u.source == "meta" and u.kinds == ["bridges"]  # stairs is an Avoid kind, lava nothing
    assert u.places == [{"id": "way/1", "name": "Times Square"}] and u.missing == ["Atlantis"]
    assert u.labels == ["bridges", "Times Square"]
    assert "Couldn't find “Atlantis” on our map." in u.note and "No map data for shade" in u.note


def test_crowds_become_transit_hubs_and_say_so(model):
    model["answer"] = {"kinds": [], "places": [], "count": None, "unsupported": ["crowds"]}
    u = understand("avoid", "crowds")
    assert u.kinds == ["transit_hubs"] and u.unsupported == []
    assert "No crowd data" in u.note


def test_stops_get_a_count(model):
    model["answer"] = {"kinds": ["cafes", "bakeries"], "places": [], "count": None, "unsupported": []}
    assert understand("stops", "coffee and a croissant").count == 2
    model["answer"] = {"kinds": ["cafes"], "places": [], "count": 3, "unsupported": []}
    assert understand("stops", "three coffees").count == 3
    model["answer"] = {"kinds": [], "places": [], "count": 2, "unsupported": ["restrooms"]}
    u = understand("stops", "two restrooms")
    assert u.count == 0 and "restrooms" in u.note


def test_of_several_places_by_one_name_the_nearest(model):
    model["answer"] = {"kinds": [], "places": ["Starbucks"], "count": None, "unsupported": []}
    assert understand("pass", "Starbucks", origin=(40.749, -73.981)).places[0]["id"] == "node/4"
    custom_options._cache.clear()
    assert understand("pass", "Starbucks", origin=(40.701, -74.001)).places[0]["id"] == "node/3"


def test_the_model_gets_only_the_words(model):
    model["answer"] = {"kinds": [], "places": ["Starbucks"], "count": None, "unsupported": []}
    resp = client.post("/api/options/understand", json={"field": "pass", "text": "Starbucks",
                                                         "origin": {"lat": 40.7493, "lon": -73.9812}})
    assert resp.status_code == 200 and resp.json()["places"][0]["id"] == "node/4"
    sent = "".join(model["sent"])
    assert "40.74" not in sent and "73.98" not in sent and "node/" not in sent


def test_the_api_checks_the_request():
    assert client.post("/api/options/understand", json={"field": "pass", "text": ""}).status_code == 422
    assert client.post("/api/options/understand", json={"field": "hats", "text": "x"}).status_code == 422
    assert client.post("/api/options/understand", json={"field": "pass", "text": "x" * 81}).status_code == 422


def test_a_place_to_avoid_bends_the_route(tmp_path):
    from app.core.geo import haversine_m

    g, dlon = grid_graph(tmp_path / "g.npz")
    a, b = (LAT0, LON0), (LAT0, LON0 + 4 * dlon)  # along the bottom street
    mid = (LAT0, LON0 + 2 * dlon)
    plain = LocalRouting(g).walk(a, b)
    away = LocalRouting(g).view(avoid_near=(mid,)).walk(a, b)
    near = lambda leg: min(haversine_m(*p, *mid) for p in leg.geometry)  # noqa: E731
    assert near(plain) < 1 and near(away) > AVOID_NEAR_M
    assert away.duration_min > plain.duration_min  # the real walking time, not the penalized cost


def test_typed_stops_are_only_of_the_kinds_named():
    from app.services.options import describe, mark_stops

    cafe = Place(id="node/9", name="Mid Cafe", lat=LAT0, lon=LON0 + 0.006, category="cafe")

    class Index:
        def within(self, lat, lon, r):
            from app.core.geo import haversine_m
            return [cafe] if haversine_m(lat, lon, cafe.lat, cafe.lon) <= r else []

    class Places:
        class snapshot:
            destination = Index()

    geometry = [(LAT0, LON0 + k * 0.001) for k in range(13)]
    park = {"id": "w/1", "name": "Park", "category": "park", "lat": LAT0, "lon": LON0 + 0.004, "along_m": 340}
    legs = [RouteLeg(geometry=geometry, distance_m=1010, duration_min=12.6, pois=[park])]
    stops = mark_stops(legs, 2, ["cafes"], Places(), only=True)
    assert [s["name"] for s in stops] == ["Mid Cafe"]  # the park is not a coffee
    twin = {**park, "id": "w/2", "name": "Mid Cafe", "category": "cafe", "along_m": 900}
    legs = [RouteLeg(geometry=geometry, distance_m=1010, duration_min=12.6, pois=[twin])]
    assert [s["name"] for s in mark_stops(legs, 2, ["cafes"], Places(), only=True)] == ["Mid Cafe"]  # one of a name
    assert mark_stops(legs, 2, ["cafes"], Places(), only=True, not_named="Mid Cafe") == []  # nor the walk's end
    assert describe([], stops, 2, [], ["cafes"]).endswith(
        "Only 1 of the 2 stops asked for: this route passes fewer cafes right on the way.")
