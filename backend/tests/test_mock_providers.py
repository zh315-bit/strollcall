import json

import pytest

from app.core.budget import BudgetExceeded
from app.core.errors import ProviderError
from app.providers import get_meta, meta_or_mock
from app.providers.meta import MetaError
from app.providers.mock import MockMeta, MockORS, MockOverpass

from .test_meta_provider import wav_bytes

# Small hand-written test data; real captured data lives in fixtures/.
PLACES = [
    {"id": "node/1", "name": "Near Cafe", "lat": 40.7310, "lon": -73.9970, "category": "cafe"},
    {"id": "way/2", "name": "Near Park", "lat": 40.7315, "lon": -73.9975, "category": "park"},
    {"id": "node/3", "name": "Far Books", "lat": 40.7600, "lon": -73.9800, "category": "bookstore"},
]
LEG = {"geometry": [[40.731, -73.997], [40.735, -73.991]], "distance_m": 700.0, "duration_min": 8.4}


@pytest.fixture
def fixtures_dir(tmp_path):
    (tmp_path / "sample_places.json").write_text(json.dumps(PLACES))
    routes = [{"key": "40.7310,-73.9970|40.7350,-73.9910", "leg": LEG}]
    (tmp_path / "sample_routes.json").write_text(json.dumps(routes))
    (tmp_path / "mock_meta.json").write_text(
        json.dumps({"walk_intent": {"duration_min": 30}, "transcript": "hi"})
    )
    return tmp_path


def test_mock_overpass_filters_by_radius_and_category(fixtures_dir):
    mock = MockOverpass(fixtures_dir)
    assert {p.id for p in mock.places_near(40.731, -73.997, 500)} == {"node/1", "way/2"}
    assert [p.id for p in mock.places_near(40.731, -73.997, 500, ["park"])] == ["way/2"]


def test_mock_ors_returns_captured_leg_only(fixtures_dir):
    mock = MockORS(fixtures_dir)
    leg = mock.walk((40.73101, -73.99702), (40.73499, -73.99098))
    assert leg.duration_min == 8.4
    with pytest.raises(ProviderError) as e:
        mock.walk((40.70, -74.00), (40.71, -74.01))
    assert e.value.code == "routing_unavailable"


def test_mock_meta(fixtures_dir):
    mock = MockMeta(fixtures_dir)
    assert mock.structured_json("s", "u", {}, name="walk_intent") == {"duration_min": 30}
    assert mock.transcribe(wav_bytes(), "audio/wav") == "hi"
    assert mock.generate_image("x").startswith(b"\x89PNG")
    with pytest.raises(MetaError):
        mock.structured_json("s", "u", {}, name="unknown")


def test_use_mocks_switches_meta():
    assert get_meta().name == "mock"


def test_budget_exceeded_falls_back_to_mock(monkeypatch, caplog):
    class BrokeMeta:
        name = "meta"

        def structured_json(self, *a, **k):
            raise BudgetExceeded("daily Meta budget $15.00 reached")

    monkeypatch.setattr("app.providers.get_meta", lambda: BrokeMeta())
    result, source = meta_or_mock(lambda m: m.structured_json("s", "u", {}, name="walk_intent"))
    assert source == "mock"
    assert result["duration_min"] == 25
    assert "Falling back to mock" in caplog.text


def test_mocks_read_committed_fixtures():
    """The fixtures in the repo load and are usable offline."""
    from app.providers import get_ors, get_overpass

    places = get_overpass().places_near(40.73089, -73.99759, 500)
    assert places and all(p.category in {"park", "cafe", "bookstore", "landmark"} for p in places)
    assert parse_ok(get_meta().structured_json("s", "u", {}, name="walk_intent"))
    assert get_ors().name == "mock"


def parse_ok(data):
    from app.models.schemas import WalkIntent

    return WalkIntent.model_validate(data)


def test_mock_ors_serves_captured_smoke_route():
    from app.providers import get_ors

    leg = get_ors().walk((40.73089, -73.99759), (40.73576, -73.99065))
    assert leg.duration_min > 0 and len(leg.geometry) > 2
