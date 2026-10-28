"""Place-feature grounding, using explanations Muse Spark actually wrote on 2026-10-28."""

import pytest

from app.models.schemas import Place, WalkIntent
from app.services.grounding import place_evidence, preference_text, unsupported


def place(name, category, **tags):
    return Place(id=name, name=name, lat=40.73, lon=-73.99, category=category, tags=tags)


WSP, BAGELS = place("Washington Square Park", "park"), place("Tompkins Square Bagels", "cafe")
GOULD = place("Gould Plaza", "plaza")
GAY, LALA = place("Gay Street", "plaza"), place("LÀ LÁ Bakeshop", "bakery")
P1 = preference_text(WalkIntent(duration_min=25, vibes=["quiet"], endpoint_type="cafe"),
                     WalkIntent(duration_min=30, vibes=["green"], endpoint_type="park", avoid=["traffic"]))
P6 = preference_text(WalkIntent(duration_min=30, vibes=["lively"], endpoint_type="bakery"),
                     WalkIntent(duration_min=25, vibes=["quiet"]))


@pytest.mark.parametrize("text,places,prefs", [
    ("Meets at park for B's park/green wish and ends at cafe for A's cafe wish.", [WSP, BAGELS], P1),
    ("Ends at cafe for A with balanced 8 and 7 walks and 0.7 gap, though plaza not park for B.", [GOULD, BAGELS], P1),
    ("A's cafe and B's bookstore are both acceptable endings.", [],
     "cafe bookstore quiet"),
    ("Balance A's lively bakery preference with B's quiet preference.", [], P6),
])
def test_grounded_explanations_pass(text, places, prefs):
    assert unsupported(text, place_evidence(places), prefs) == []


@pytest.mark.parametrize("text,places,prefs,expected", [
    ("Bakery suits A's lively bakery wish, 32 total with 16 together blends quiet stretches for B.",
     [GAY, LALA], P6, "route claim"),
    ("Ends at a cafe for A, with a park on the way for B.", [], P1, "route claim"),
    ("Blend lively sections for A with quieter stretches for B.", [], P6, "route claim"),
    ("A short walk to the waterfront, then coffee.", [GOULD, BAGELS], P1, "feature not in data: water"),
    ("The plaza is quiet and safe in the afternoon.", [GOULD, BAGELS], P1, "unverifiable claim"),
    ("Shady benches at the meeting point.", [GOULD, BAGELS], P1, "feature not in data: seating"),
])
def test_ungrounded_explanations_fail(text, places, prefs, expected):
    problems = unsupported(text, place_evidence(places), prefs)
    assert any(expected in p for p in problems), problems


def test_tags_and_names_count_as_evidence():
    ev = place_evidence([place("Pier 45 Overlook", "landmark", tourism="viewpoint"),
                         place("Cafe X", "cafe", outdoor_seating="yes")])
    assert {"viewpoint", "seating", "cafe", "landmark", "water"} <= ev


def test_avoiding_something_is_a_preference_not_a_claim():
    assert unsupported("The walk tries to avoid traffic.", set(), P1) == []
    assert unsupported("There is little traffic on this route.", set(), P1) != []
