"""negotiate() and the Meta ranking (rung 1), on fixture plans, with fake and mock Meta."""

import sys
from pathlib import Path

import pytest

from app.core.budget import BudgetExceeded
from app.models.schemas import JointPreference, WalkIntent
from app.providers import get_ors, get_overpass
from app.services import explain
from app.services.intent import combined_intent, default_negotiation, negotiate
from app.services.planner import plan_walk

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from _common import load_cases  # noqa: E402

A = WalkIntent(duration_min=25, vibes=["quiet"], endpoint_type="cafe")
B = WalkIntent(duration_min=30, vibes=["quiet", "green"], endpoint_type="park", avoid=["traffic"],
               hard_constraints=["step-free"])
JOINT = JointPreference(shared_vibes=["quiet"], a_priorities=["cafe"], b_priorities=["green"],
                        compromises=[])


class FakeMeta:
    name = "meta"

    def __init__(self, result=None, error=None):
        self.result, self.error = result, error
        self.calls = []

    def structured_json(self, system, user, schema, name="result"):
        self.calls.append((name, user, schema))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def use_meta(monkeypatch):
    def install(fake):
        monkeypatch.setattr("app.providers.get_meta", lambda: fake)
        return fake
    return install


@pytest.fixture
def p1_plan():
    case = next(c for c in load_cases() if c["id"] == "p1")
    return plan_walk(case["a"], case["b"], case["intent"], get_overpass(), get_ors(), case["depart_at"])


# --- negotiation ---

def test_negotiate_with_meta_keeps_only_vibes_both_gave(use_meta):
    use_meta(FakeMeta({
        "shared_vibes": ["Quiet", "green"], "a_priorities": ["ends at a cafe"],
        "b_priorities": ["green", "avoid traffic"], "compromises": ["A's cafe and B's park are both acceptable endings."],
        "tradeoff": "Both want quiet; A's cafe and B's green wish are weighed equally.",
    }))
    result = negotiate(A, B)
    assert result.source == "meta"
    assert result.joint.shared_vibes == ["quiet"]  # "green" was only B's
    assert result.tradeoff.startswith("Both want quiet")


def test_negotiate_falls_back_when_meta_fails(use_meta):
    from app.providers.meta import MetaInvalidJSON

    use_meta(FakeMeta(error=MetaInvalidJSON("bad")))
    result = negotiate(A, B)
    assert result.source == "default" and result.note == "model_unavailable"
    assert result.joint.shared_vibes == ["quiet"]
    assert "green" in result.joint.b_priorities and "avoid traffic" in result.joint.b_priorities
    assert any("cafe" in c and "park" in c for c in result.joint.compromises)


def test_negotiate_rejects_bad_shape(use_meta):
    use_meta(FakeMeta({"shared_vibes": "quiet"}))
    assert negotiate(A, B).note == "invalid_model_output"


def test_negotiate_mock_is_labelled():
    result = negotiate(A, B)
    assert result.source == "mock" and result.tradeoff.startswith("Mock data")


def test_budget_cap_negotiation_uses_mock(use_meta):
    use_meta(FakeMeta(error=BudgetExceeded("cap")))
    assert negotiate(A, B).source == "mock"


def test_combined_intent_never_relaxes_hard_limits():
    c = combined_intent(A, B)
    assert c.duration_min == 25  # the shorter budget
    assert c.hard_constraints == ["step-free"] and c.avoid == ["traffic"]
    assert c.endpoint_type is None  # cafe vs park conflict
    assert combined_intent(A, WalkIntent(duration_min=30)).endpoint_type == "cafe"


def test_default_negotiation_has_no_meta_text():
    d = default_negotiation(A, A, "x")
    assert d.joint.compromises == [] and d.source == "default"


# --- ranking ---

def ranking(*items):
    return {"ranking": [{"id": i, "reason": r} for i, r in items]}


def test_meta_reorders_supplied_candidates_only(use_meta, p1_plan):
    fake = use_meta(FakeMeta(ranking(("c2", "Shortest gap, fair for both."),
                                     ("c1", "Park start suits B's quiet wish."),
                                     ("c3", "Fine but less central."))))
    result = explain.rank_candidates(p1_plan, A, B, JOINT)
    assert result.source == "meta"
    assert [c.id for c in result.candidates] == [p1_plan.candidates[i].id for i in (1, 0, 2)]
    assert result.reasons[p1_plan.candidates[1].id] == "Shortest gap, fair for both."
    _, user, schema = fake.calls[0]
    assert schema["properties"]["ranking"]["items"]["properties"]["id"]["enum"] == ["c1", "c2", "c3"]
    assert "node/" not in user and "way/" not in user  # model sees labels and facts, not OSM ids


def test_numbers_from_the_facts_are_accepted(use_meta, p1_plan):
    c1 = p1_plan.candidates[0]
    reason = f"A walks {round(c1.a_leg.duration_min)} min and B {round(c1.b_leg.duration_min)} min; it fits."
    use_meta(FakeMeta(ranking(("c1", reason), ("c2", "ok"), ("c3", "ok"))))
    assert explain.rank_candidates(p1_plan, A, B, JOINT).source == "meta"


@pytest.mark.parametrize("data,note", [
    (ranking(("c1", "x"), ("c2", "y")), "ranking_ids_mismatch"),
    (ranking(("c1", "x"), ("c1", "y"), ("c3", "z")), "ranking_ids_mismatch"),
    (ranking(("c1", "Only 97 minutes in total."), ("c2", "y"), ("c3", "z")), "invented_number"),
    (ranking(("c1", "x" * 300), ("c2", "y"), ("c3", "z")), "reason_length"),
    ({"ranking": "c1"}, "invalid_model_output"),
])
def test_bad_ranking_keeps_deterministic_order(use_meta, p1_plan, data, note):
    use_meta(FakeMeta(data))
    result = explain.rank_candidates(p1_plan, A, B, JOINT)
    assert result.source == "default" and result.note == note
    assert result.candidates == p1_plan.candidates and result.reasons == {}


def test_meta_down_keeps_deterministic_order(use_meta, p1_plan):
    from app.core.errors import ProviderError

    use_meta(FakeMeta(error=ProviderError("model_unavailable", "down")))
    result = explain.rank_candidates(p1_plan, A, B, JOINT)
    assert result.source == "default" and result.candidates == p1_plan.candidates


def test_mock_ranking_is_labelled(p1_plan):
    result = explain.rank_candidates(p1_plan, A, B, JOINT)
    assert result.source == "mock"
    assert all(r.startswith("Mock data") for r in result.reasons.values())


def test_negotiation_route_promise_is_discarded(use_meta):
    use_meta(FakeMeta({
        "shared_vibes": ["quiet"], "a_priorities": ["cafe"], "b_priorities": ["green"],
        "compromises": ["Ends at a cafe for A, with a park on the way for B."],
        "tradeoff": "Quiet streets for both.",
    }))
    result = negotiate(A, B)
    assert result.source == "default" and result.note == "unsupported_feature"


def test_ranking_with_ungrounded_feature_keeps_deterministic_order(use_meta, p1_plan):
    use_meta(FakeMeta(ranking(("c1", "Right by the waterfront."), ("c2", "ok"), ("c3", "ok"))))
    result = explain.rank_candidates(p1_plan, A, B, JOINT)
    assert result.source == "default" and result.note == "unsupported_feature"
    assert result.candidates == p1_plan.candidates


def test_wish_descriptions_count_as_preferences_for_grounding(use_meta, p1_plan):
    from app.services.wishes import Wish, Wishes

    wishes = Wishes(items=[Wish(requirement="green_meetup", who="B", quote="green")], source="meta")
    reason = "Meets B's park wish and ends at a cafe for A."
    # c2's meetup point is not a park, so only B's wish can back the word "park".
    use_meta(FakeMeta(ranking(("c1", "ok"), ("c2", reason), ("c3", "ok"))))
    assert p1_plan.places[p1_plan.candidates[1].meeting_place_id].category != "park"
    a = WalkIntent(duration_min=25, endpoint_type="cafe")
    b = WalkIntent(duration_min=25, vibes=["green"])
    assert explain.rank_candidates(p1_plan, a, b, JOINT, wishes).source == "meta"
    assert explain.rank_candidates(p1_plan, a, b, JOINT).note == "unsupported_feature"


def test_combined_strictness_follows_the_shorter_budget():
    only20 = WalkIntent(duration_min=20, duration_strict=True)
    forty = WalkIntent(duration_min=40)
    assert combined_intent(only20, forty).duration_strict is True
    assert combined_intent(WalkIntent(duration_min=20), WalkIntent(duration_min=40, duration_strict=True)).duration_strict is False


def test_comparative_numbers_are_allowed_internal_labels_are_not(use_meta, p1_plan):
    c1, c2 = p1_plan.candidates[0], p1_plan.candidates[1]
    diff = abs(round(c1.total_elapsed_min) - round(c2.total_elapsed_min))
    other = p1_plan.places[c2.endpoint_place_id].name
    reason = f"{diff} min different from the {other} plan, same start for both."
    use_meta(FakeMeta(ranking(("c1", reason), ("c2", "ok"), ("c3", "ok"))))
    assert explain.rank_candidates(p1_plan, A, B, JOINT).source == "meta"
    use_meta(FakeMeta(ranking(("c1", "Better than c2."), ("c2", "ok"), ("c3", "ok"))))
    assert explain.rank_candidates(p1_plan, A, B, JOINT).note == "internal_label_in_reason"


def test_digits_in_place_names_are_not_numbers(use_meta, p1_plan):
    name = p1_plan.places[p1_plan.candidates[0].endpoint_place_id].name
    use_meta(FakeMeta(ranking(("c1", f"Ends at {name} for A."), ("c2", "ok"), ("c3", "ok"))))
    from app.models.schemas import Place

    p1_plan.places[p1_plan.candidates[0].endpoint_place_id] = Place(
        **{**p1_plan.places[p1_plan.candidates[0].endpoint_place_id].model_dump(), "name": "787 Coffee Co."})
    use_meta(FakeMeta(ranking(("c1", "Ends at 787 Coffee Co. for A."), ("c2", "ok"), ("c3", "ok"))))
    assert explain.rank_candidates(p1_plan, A, B, JOINT).source == "meta"
