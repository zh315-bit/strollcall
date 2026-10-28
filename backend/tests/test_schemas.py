from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.schemas import Invite, JointPreference, RouteLeg, WalkIntent


def test_walk_intent_defaults():
    intent = WalkIntent(duration_min=25)
    assert intent.vibes == [] and intent.endpoint_type is None


@pytest.mark.parametrize("minutes", [5, 14, 61, 120])
def test_walk_intent_rejects_out_of_range_duration(minutes):
    with pytest.raises(ValidationError):
        WalkIntent(duration_min=minutes)


def test_walk_intent_requires_duration():
    with pytest.raises(ValidationError):
        WalkIntent.model_validate({"vibes": ["quiet"]})


def test_joint_preference_requires_all_fields():
    with pytest.raises(ValidationError):
        JointPreference(shared_vibes=[], a_priorities=[], b_priorities=[])


def test_invite_roundtrip():
    invite = Invite(
        token="t",
        status="pending",
        expires_at=datetime(2026, 10, 29, tzinfo=timezone.utc),
        invite_text="Walk?",
        a_intent=WalkIntent(duration_min=25),
    )
    assert Invite.model_validate_json(invite.model_dump_json()) == invite


def test_route_leg_geometry_pairs():
    leg = RouteLeg(geometry=[[40.73, -73.99], [40.74, -73.98]], distance_m=1200, duration_min=15)
    assert leg.geometry[0] == (40.73, -73.99)
