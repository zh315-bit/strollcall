import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def offline_settings(monkeypatch, tmp_path):
    """Every test runs on mocks, with a throwaway SQLite file and no real keys."""
    monkeypatch.setenv("USE_MOCKS", "true")
    monkeypatch.setenv("MODEL_API_KEY", "")
    monkeypatch.setenv("ORS_API_KEY", "")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
