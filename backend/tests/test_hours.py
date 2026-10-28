from datetime import datetime

import pytest

from app.core.hours import is_open, is_open_during

WED_10 = datetime(2026, 10, 28, 10, 0)  # a Wednesday
SAT_10 = datetime(2026, 10, 31, 10, 0)
THU_01 = datetime(2026, 10, 29, 1, 0)


@pytest.mark.parametrize("hours,at,expected", [
    ("24/7", WED_10, True),
    ("Mo-Fr 08:00-18:00", WED_10, True),
    ("Mo-Fr 08:00-18:00", SAT_10, False),  # unmentioned day is closed
    ("Mo-Fr 11:00-18:00", WED_10, False),
    ("Mo-Fr 08:00-12:00,14:00-18:00; Sa-Su off", SAT_10, False),
    ("We-Fr 07:00-15:00; Sa-Su 08:00-16:00", SAT_10, True),
    ("Mo-Su 08:00-18:00; We off", WED_10, False),  # later rule wins
    ("Mo-Su 18:00-02:00", THU_01, True),  # past midnight from Wednesday
    ("Fr-Mo 10:00-16:00", datetime(2026, 11, 1, 11, 0), True),  # wrapping day range, Sunday
    ("08:00-20:00", SAT_10, True),
    (None, WED_10, None),
    ("Mo-Fr 08:00-18:00; PH off", WED_10, None),  # holidays not supported
    ("sunrise-sunset", WED_10, None),
])
def test_is_open(hours, at, expected):
    assert is_open(hours, at) is expected


def test_visit_window():
    assert is_open_during("Mo-Fr 08:00-10:30", WED_10, 25) is True
    assert is_open_during("Mo-Fr 08:00-10:15", WED_10, 25) is False
    assert is_open_during(None, WED_10, 25) is None
