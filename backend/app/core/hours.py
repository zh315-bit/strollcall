"""A small evaluator for the common subset of OSM opening_hours.

Supported: "24/7", rules separated by ";" of the form "[days] [times|off|closed]", with
day ranges/lists (Mo-Fr, Sa,Su) and time ranges (08:00-18:00, 18:00-02:00, several
separated by ","). A later rule replaces earlier ones for the days it names, as in OSM.
Anything else (holidays, months, sunrise, "+", comments) makes the result unknown (None):
we never guess that a place is open or closed.
"""

import re
from datetime import datetime, timedelta

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
DAY_RE = re.compile(r"^(Mo|Tu|We|Th|Fr|Sa|Su)(-(Mo|Tu|We|Th|Fr|Sa|Su))?$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


class Unsupported(Exception):
    pass


def _days(spec: str) -> set[int]:
    days: set[int] = set()
    for part in spec.split(","):
        m = DAY_RE.match(part.strip())
        if not m:
            raise Unsupported(part)
        start = DAYS.index(m.group(1))
        end = DAYS.index(m.group(3)) if m.group(3) else start
        i = start
        while True:
            days.add(i)
            if i == end:
                break
            i = (i + 1) % 7
    return days


def _ranges(spec: str) -> list[tuple[int, int]]:
    ranges = []
    for part in spec.split(","):
        m = TIME_RE.match(part.strip())
        if not m:
            raise Unsupported(part)
        h1, m1, h2, m2 = (int(x) for x in m.groups())
        ranges.append((h1 * 60 + m1, h2 * 60 + m2))
    return ranges


def _schedule(value: str) -> dict[int, list[tuple[int, int]]]:
    """Day index -> open minute ranges (end may exceed 1440 for past-midnight hours)."""
    value = value.strip()
    if value == "24/7":
        return {d: [(0, 1440)] for d in range(7)}
    schedule: dict[int, list[tuple[int, int]]] = {}
    for rule in filter(None, (r.strip() for r in value.split(";"))):
        tokens = rule.split(None, 1)
        if DAY_RE.match(tokens[0].split(",")[0]):
            days = _days(tokens[0])
            rest = tokens[1].strip() if len(tokens) > 1 else ""
        else:
            days, rest = set(range(7)), rule
        if rest in ("off", "closed"):
            ranges = []
        elif rest:
            ranges = [(s, e if e > s else e + 1440) for s, e in _ranges(rest)]
        else:
            raise Unsupported(rule)
        for d in days:
            schedule[d] = ranges
    return schedule


def is_open(opening_hours: str | None, at: datetime) -> bool | None:
    """True / False, or None when the hours are missing or not understood."""
    if not opening_hours:
        return None
    try:
        schedule = _schedule(opening_hours)
    except Unsupported:
        return None
    minute = at.hour * 60 + at.minute
    today, yesterday = at.weekday(), (at.weekday() - 1) % 7
    if today in schedule and any(s <= minute < e for s, e in schedule[today]):
        return True
    # A range from yesterday that runs past midnight.
    if yesterday in schedule and any(e > 1440 and minute < e - 1440 for _, e in schedule[yesterday]):
        return True
    return False  # in OSM, days no rule mentions are closed


def is_open_during(opening_hours: str | None, start: datetime, minutes: float) -> bool | None:
    """Open at both ends of a visit window (an approximation that ignores mid-day breaks)."""
    a = is_open(opening_hours, start)
    b = is_open(opening_hours, start + timedelta(minutes=minutes))
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True
