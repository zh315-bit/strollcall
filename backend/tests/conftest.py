import socket

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def offline_settings(monkeypatch, tmp_path):
    """Every test runs on mocks, with a throwaway SQLite file and no real keys."""
    monkeypatch.setenv("USE_MOCKS", "true")
    monkeypatch.setenv("MODEL_API_KEY", "")
    monkeypatch.setenv("ORS_API_KEY", "")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("STROLLCALL_CALLER", raising=False)  # scripts/_common sets it on import
    get_settings.cache_clear()
    assert get_settings().use_mocks, "tests must run with USE_MOCKS=true"
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail any test that tries to open a real network connection."""

    def blocked(*args, **kwargs):
        raise RuntimeError("network access is disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
