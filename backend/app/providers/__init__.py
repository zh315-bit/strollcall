"""Provider factories. USE_MOCKS=true switches every provider to its fixture-backed twin."""

import logging
from collections.abc import Callable
from typing import TypeVar

from app.core.budget import BudgetExceeded
from app.core.config import get_settings
from app.providers.mock import MockMeta

log = logging.getLogger(__name__)
T = TypeVar("T")


def get_meta():
    if get_settings().use_mocks:
        return MockMeta()
    from app.providers.meta import MetaProvider

    return MetaProvider()


def meta_or_mock(call: Callable[[object], T]) -> tuple[T, str]:
    """Run `call` against the Meta provider; past the daily cap, run it against the mock.

    Returns (result, source) where source is "meta" or "mock".
    """
    meta = get_meta()
    if meta.name == "mock":
        return call(meta), "mock"
    try:
        return call(meta), "meta"
    except BudgetExceeded as e:
        log.warning("Meta budget guard: %s. Falling back to mock Meta provider.", e)
        return call(MockMeta()), "mock"


_overpass = None


def get_overpass():
    global _overpass
    if get_settings().use_mocks:
        from app.providers.mock import MockOverpass

        return MockOverpass()
    if _overpass is None:  # one instance so its cache is shared
        from app.providers.overpass import OverpassProvider

        _overpass = OverpassProvider()
    return _overpass
