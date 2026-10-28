from app.core.config import get_settings


def test_defaults_and_env_override(monkeypatch):
    monkeypatch.setenv("DAILY_BUDGET_USD", "3.5")
    get_settings.cache_clear()
    s = get_settings()
    assert s.model_base_url == "https://api.meta.ai/v1"
    assert s.model_id == "muse-spark-1.3"
    assert s.daily_budget_usd == 3.5
    assert s.use_mocks is True


def test_key_is_not_printed(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "sk-should-not-leak")
    get_settings.cache_clear()
    s = get_settings()
    assert "sk-should-not-leak" not in repr(s)
    assert s.model_api_key.get_secret_value() == "sk-should-not-leak"
