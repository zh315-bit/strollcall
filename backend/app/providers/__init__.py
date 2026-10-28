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


_ors = None


def get_ors():
    global _ors
    if get_settings().use_mocks:
        from app.providers.mock import MockORS

        return MockORS()
    if _ors is None:
        from app.providers.ors import ORSProvider

        _ors = ORSProvider()
    return _ors


def _ors_or_none():
    """ORS as a fallback outside the local map; None if it cannot be created (no key)."""
    from app.core.errors import ProviderError

    try:
        return get_ors()
    except ProviderError:
        return None


_routing = None


def get_routing():
    """ROUTING_PROVIDER = local (default) | ors | mock. USE_MOCKS=true forces mock."""
    global _routing
    s = get_settings()
    kind = "mock" if s.use_mocks else s.routing_provider
    if kind == "mock":
        from app.providers.mock import MockORS

        return MockORS()
    if kind == "ors":
        return get_ors()
    if _routing is None:
        from app.providers.local_routing import LocalRouting, load_graph

        _routing = LocalRouting(load_graph(s.graph_path), fallback=_ors_or_none)
    return _routing


_places = None


def get_places():
    """PLACES_PROVIDER = snapshot (default) | overpass | mock. USE_MOCKS=true forces mock."""
    global _places
    s = get_settings()
    kind = "mock" if s.use_mocks else s.places_provider
    if kind == "mock":
        from app.providers.mock import MockOverpass

        return MockOverpass()
    if kind == "overpass":
        return get_overpass()
    if _places is None:
        from app.providers.snapshot_places import SnapshotPlaces, load_snapshot

        _places = SnapshotPlaces(load_snapshot(s.places_snapshot_path), fallback=get_overpass)
    return _places
