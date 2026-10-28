import pytest

from app.core.budget import BudgetExceeded, SpendGuard, image_cost, text_cost, voice_cost


def test_prices():
    assert text_cost(1_000_000, 0) == pytest.approx(1.25)
    assert text_cost(1_000_000, 1_000_000, cached_tokens=1_000_000) == pytest.approx(0.15 + 4.25)
    assert image_cost(2) == pytest.approx(0.02)
    assert voice_cost(3_600_999) == pytest.approx(0.18)  # whole seconds, rounded down


def test_cutoff_at_daily_cap():
    guard = SpendGuard(daily_cap_usd=0.05)
    assert guard.today_total() == 0
    guard.record("image", "muse-image-1.0", 0.04)
    assert guard.today_total() == pytest.approx(0.04)
    assert guard.can_spend(0.01)
    assert not guard.can_spend(0.02)
    with pytest.raises(BudgetExceeded):
        guard.check(0.02)
