"""Invite lifecycle: pending -> planning -> proposed -> confirmed, or expired / error.

Privacy: exact origins, owner keys and raw texts live in a private row that no response
returns and that is deleted on expiry. A plan shows each person their own full leg; the
other person's leg is shown without its first TRIM_M meters, so it does not reveal where
they started. Nothing here logs coordinates.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.core.errors import ProviderError
from app.core.geo import haversine_m
from app.models.db import load_invite, load_invite_extra, save_invite, save_invite_extra
from app.models.schemas import Invite, MeetupCandidate, Place, RouteLeg, WalkIntent

log = logging.getLogger(__name__)

INVITE_TTL = timedelta(hours=24)
TRIM_M = 200.0
NYC = ZoneInfo("America/New_York")


class InviteView(BaseModel):
    """What a page gets: the Invite plus plan details, never an exact origin."""

    token: str
    role: str  # a / b / guest
    status: str
    expires_at: datetime
    invite_text: str
    a_intent: WalkIntent
    b_intent: WalkIntent | None = None
    candidates: list[MeetupCandidate] = []
    selected_id: str | None = None
    error: str | None = None
    places: dict[str, Place] = {}
    tradeoff: str | None = None
    reasons: dict[str, str] = {}  # candidate id -> Meta's reason (validated)
    failure: dict | None = None  # no_feasible_plan: binding constraint and suggestion
    image_url: str | None = None
    sources: dict[str, str] = {}  # what produced each part: meta / mock / default / local / snapshot ...
    demo_data: bool = False  # true if any visible part is mock or template data


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create(a_intent: WalkIntent, a_origin: tuple[float, float], a_text: str = "") -> tuple[Invite, str]:
    from app.services.invite_card import invite_text

    text, text_source = invite_text(a_intent, a_text)
    invite = Invite(token=secrets.token_urlsafe(16), status="pending", expires_at=_now() + INVITE_TTL,
                    invite_text=text, a_intent=a_intent)
    a_key = secrets.token_urlsafe(16)
    save_invite(invite)
    save_invite_extra(
        invite.token,
        {"sources": {"invite_text": text_source, "image": "pending"}},
        {"a_origin": list(a_origin), "a_key": a_key, "a_text": a_text[:500]},
    )
    return invite, a_key


def make_image(token: str) -> None:
    """Background: the Muse Image card illustration."""
    from app.services.invite_card import make_card_image

    invite = load_invite(token)
    if invite is None:
        return
    source = make_card_image(token, invite.a_intent)
    public, private = load_invite_extra(token)
    public.setdefault("sources", {})["image"] = source
    save_invite_extra(token, public, private)


def _expire_if_due(invite: Invite) -> Invite:
    if invite.status != "expired" and _now() >= invite.expires_at:
        invite.status = "expired"
        save_invite(invite)
        public, _ = load_invite_extra(invite.token)
        save_invite_extra(invite.token, public, None)  # origins, keys and texts deleted
    return invite


def role_of(token: str, key: str | None) -> str:
    _, private = load_invite_extra(token)
    if not private or not key:
        return "guest"
    if secrets.compare_digest(key, private.get("a_key", "")):
        return "a"
    if private.get("b_key") and secrets.compare_digest(key, private["b_key"]):
        return "b"
    return "guest"


def trim_start(leg: RouteLeg, meters: float = TRIM_M) -> RouteLeg:
    """Drop the first `meters` of a leg's geometry (times stay the same)."""
    pts, walked = leg.geometry, 0.0
    for i in range(1, len(pts)):
        walked += haversine_m(*pts[i - 1], *pts[i])
        if walked >= meters:
            return leg.model_copy(update={"geometry": pts[i:]})
    return leg.model_copy(update={"geometry": pts[-1:]})


def view(token: str, key: str | None = None) -> InviteView | None:
    invite = load_invite(token)
    if invite is None:
        return None
    invite = _expire_if_due(invite)
    role = role_of(token, key)
    public, _ = load_invite_extra(token)
    candidates = []
    for c in invite.candidates:
        update = {}
        if role != "a":
            update["a_leg"] = trim_start(c.a_leg)
        if role != "b":
            update["b_leg"] = trim_start(c.b_leg)
        candidates.append(c.model_copy(update=update))
    sources = public.get("sources", {})
    image_ready = sources.get("image") in ("meta", "mock")
    return InviteView(
        token=invite.token, role=role, status=invite.status, expires_at=invite.expires_at,
        invite_text=invite.invite_text, a_intent=invite.a_intent, b_intent=invite.b_intent,
        candidates=candidates, selected_id=invite.selected_id, error=invite.error,
        places=public.get("places", {}), tradeoff=public.get("tradeoff"), reasons=public.get("reasons", {}),
        failure=public.get("failure"),
        image_url=f"/api/invites/{token}/card" if image_ready else None,
        sources=sources, demo_data=any(v in ("mock", "default") for v in sources.values()),
    )


class InviteError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def accept(token: str, b_origin: tuple[float, float], b_text: str = "") -> str:
    invite = load_invite(token)
    if invite is None:
        raise InviteError(404, "invite not found")
    invite = _expire_if_due(invite)
    if invite.status == "expired":
        raise InviteError(410, "this invite has expired")
    if invite.status != "pending":
        raise InviteError(409, "this invite was already accepted")
    public, private = load_invite_extra(token)
    b_key = secrets.token_urlsafe(16)
    private.update({"b_origin": list(b_origin), "b_key": b_key, "b_text": b_text[:500]})
    invite.status = "planning"
    save_invite(invite)
    save_invite_extra(token, public, private)
    return b_key


def run_planning(token: str) -> None:
    """Background: B's preference, negotiation, wishes, planner, Meta ranking."""
    from app.providers import get_places, get_routing
    from app.services.explain import rank_candidates
    from app.services.intent import negotiate, parse_intent
    from app.services.planner import plan_for_two
    from app.services.wishes import interpret_wishes

    invite = load_invite(token)
    public, private = load_invite_extra(token)
    if invite is None or private is None or invite.status != "planning":
        return
    a = invite.a_intent
    sources = public.setdefault("sources", {})
    if private.get("b_text"):
        parsed = parse_intent(private["b_text"])
        b, sources["b_intent"] = parsed.intent, parsed.source
    else:
        b = WalkIntent(duration_min=a.duration_min)  # B gave no preference: no extra limits
    invite.b_intent = b
    try:
        places, routing = get_places(), get_routing()
        sources["routing"], sources["places"] = routing.name, places.name
        neg = negotiate(a, b)
        sources["negotiation"] = neg.source
        wishes = None
        if private.get("a_text") or private.get("b_text"):
            wishes = interpret_wishes(private.get("a_text", ""), private.get("b_text", ""))
            sources["wishes"] = wishes.source
        plan = plan_for_two(tuple(private["a_origin"]), tuple(private["b_origin"]), a, b, neg.joint,
                            places, routing, datetime.now(NYC), wishes=wishes)
    except ProviderError as e:
        invite.status, invite.error = "error", e.code
        save_invite(invite)
        save_invite_extra(token, public, private)
        return

    if plan.status != "proposed":
        invite.status, invite.error = "error", plan.status
        public["failure"] = plan.failure.model_dump() if plan.failure else None
    else:
        ranking = rank_candidates(plan, a, b, neg.joint, wishes)
        sources["ranking"] = ranking.source
        invite.status, invite.candidates = "proposed", ranking.candidates
        public.update({"places": {k: v.model_dump(mode="json") for k, v in plan.places.items()},
                       "tradeoff": neg.tradeoff, "reasons": ranking.reasons})
    save_invite(invite)
    save_invite_extra(token, public, private)
    log.info("invite planned: %s", invite.status if not invite.error else invite.error)


def confirm(token: str, key: str | None, candidate_id: str | None) -> None:
    invite = load_invite(token)
    if invite is None:
        raise InviteError(404, "invite not found")
    if role_of(token, key) not in ("a", "b"):
        raise InviteError(403, "only A or B can confirm")
    if invite.status not in ("proposed", "confirmed"):
        raise InviteError(409, f"nothing to confirm (status {invite.status})")
    ids = [c.id for c in invite.candidates]
    chosen = candidate_id or ids[0]
    if chosen not in ids:
        raise InviteError(400, "unknown candidate")
    invite.selected_id, invite.status = chosen, "confirmed"
    save_invite(invite)
