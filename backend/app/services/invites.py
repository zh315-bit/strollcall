"""Invite lifecycle: pending -> planning -> proposed -> confirmed, or expired / error.

Privacy: exact origins, owner keys and raw texts live in a private row that no response
returns and that is deleted on expiry. A plan shows each person their own full leg; the
other person's leg is shown without its first TRIM_M meters, so it does not reveal where
they started. Nothing here logs coordinates.
"""

import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.core.errors import ProviderError
from app.core.geo import haversine_m
from app.models.db import (
    feedback_roles, load_invite, load_invite_extra, save_feedback, save_invite, save_invite_extra,
)
from app.models.schemas import Invite, MeetupCandidate, Place, RouteLeg, WalkIntent

log = logging.getLogger(__name__)

INVITE_TTL = timedelta(hours=24)
RECAP_TTL = timedelta(days=30)
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
    notes: list[str] = []  # honest limits, e.g. "We can't check crowd levels; ..."
    progress: dict | None = None  # {"step": ..., "seconds": {step: s since B accepted}}
    image_url: str | None = None
    feedback_given: bool = False  # this person already answered the after-walk survey
    sources: dict[str, str] = {}  # what produced each part: meta / mock / default / local / snapshot ...
    demo_data: bool = False  # true if any visible part is mock or template data


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event(public: dict, name: str) -> bool:
    """Timestamp a step of the invite's life once (user-test instrumentation, no data).
    Returns True if it was new, so the caller knows to save."""
    events = public.setdefault("events", {})
    if name in events:
        return False
    events[name] = _now().isoformat()
    return True


def create(a_intent: WalkIntent, a_origin: tuple[float, float], a_text: str = "",
           pass_by_ids: list[str] | None = None) -> tuple[Invite, str]:
    from app.services.invite_card import invite_text, pick_illustration
    from app.services.nearby import resolve_pass_by

    sweep_expired()
    text, text_source = invite_text(a_intent, a_text)
    image_url, image_source = pick_illustration(a_intent)
    invite = Invite(token=secrets.token_urlsafe(16), status="pending", expires_at=_now() + INVITE_TTL,
                    invite_text=text, a_intent=a_intent)
    a_key = secrets.token_urlsafe(16)
    save_invite(invite)
    save_invite_extra(
        invite.token,
        {"sources": {"invite_text": text_source, "image": image_source}, "image_url": image_url,
         # Places A asked to pass by (known places, public): a soft preference for the planner.
         "pass_by": [vars(p) for p in resolve_pass_by(pass_by_ids or [])],
         "events": {"created": _now().isoformat()}},
        {"a_origin": list(a_origin), "a_key": a_key, "a_text": a_text[:500]},
    )
    return invite, a_key


def _strip_routes(invite: Invite) -> bool:
    """Remove each person's route from their start (and its steps and places); keep only times
    and the shared leg. True if anything was removed."""
    changed = False
    empty = RouteLeg(geometry=[], distance_m=0, duration_min=0)
    for c in invite.candidates:
        for name in ("a_leg", "b_leg"):
            leg = getattr(c, name)
            if leg.geometry or leg.steps or leg.pois:
                setattr(c, name, empty.model_copy(update={"distance_m": leg.distance_m, "duration_min": leg.duration_min}))
                changed = True
    return changed


def _expire_if_due(invite: Invite) -> Invite:
    """At expiry: origins, keys and texts (the private row) are deleted, and so are the routes
    from each start point. The meeting point, destination, shared leg and times remain."""
    if _now() >= invite.expires_at and (invite.status != "expired" or _strip_routes(invite.model_copy(deep=True))):
        invite.status = "expired"
        _strip_routes(invite)
        save_invite(invite)
        public, _ = load_invite_extra(invite.token)
        save_invite_extra(invite.token, public, None)
    return invite


def sweep_expired() -> int:
    """Expire every invite past its time, even one nobody opens again; delete old recaps.
    Run at startup and on each new invite. Returns how many invites were expired or stripped."""
    from app.models.db import delete_recaps_before, invites_expired_before

    n = 0
    for token in invites_expired_before(_now().isoformat()):
        invite = load_invite(token)
        if invite is not None and (invite.status != "expired" or _strip_routes(invite.model_copy(deep=True))):
            _expire_if_due(invite)
            n += 1
    delete_recaps_before((_now() - RECAP_TTL).isoformat())
    if n:
        log.info("expiry sweep: %d invite(s) expired, start routes deleted", n)
    return n


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
    """Drop the first `meters` of a leg's geometry (times stay the same) and its turn steps,
    whose first one starts at the walker's origin."""
    pts, walked = leg.geometry, 0.0
    for i in range(1, len(pts)):
        walked += haversine_m(*pts[i - 1], *pts[i])
        if walked >= meters:
            return leg.model_copy(update={"geometry": pts[i:], "steps": [], "pois": []})
    return leg.model_copy(update={"geometry": pts[-1:], "steps": [], "pois": []})


def view(token: str, key: str | None = None) -> InviteView | None:
    invite = load_invite(token)
    if invite is None:
        return None
    invite = _expire_if_due(invite)
    role = role_of(token, key)
    public, private = load_invite_extra(token)
    if role == "guest" and invite.status == "pending" and _event(public, "opened"):
        save_invite_extra(token, public, private)  # first time someone opened the link
    candidates = []
    for c in invite.candidates:
        update = {}
        if role != "a":
            update["a_leg"] = trim_start(c.a_leg)
        if role != "b":
            update["b_leg"] = trim_start(c.b_leg)
        candidates.append(c.model_copy(update=update))
    sources = public.get("sources", {})
    return InviteView(
        token=invite.token, role=role, status=invite.status, expires_at=invite.expires_at,
        invite_text=invite.invite_text, a_intent=invite.a_intent, b_intent=invite.b_intent,
        candidates=candidates, selected_id=invite.selected_id, error=invite.error,
        places=public.get("places", {}), tradeoff=public.get("tradeoff"), reasons=public.get("reasons", {}),
        failure=public.get("failure"), notes=public.get("notes", []),
        progress=_live.get(token) or public.get("progress"),
        image_url=public.get("image_url"),
        feedback_given=role in ("a", "b") and role in feedback_roles(token),
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
    _event(public, "accepted")
    invite.status = "planning"
    save_invite(invite)
    save_invite_extra(token, public, private)
    return b_key


PROGRESS_STEPS = ("understanding", "balancing", "finding", "done")

# Progress while planning runs lives in memory (one process on the free plan); pages poll it
# every second, and writing each step to Neon cost a round trip per step. The final state is
# saved with the plan.
_live: dict[str, dict] = {}
_live_lock = threading.Lock()


def _progress(token: str, step: str, started: float, timings: dict | None = None) -> dict:
    """Record the step both pages show, with seconds since B accepted."""
    import time

    with _live_lock:
        prog = _live.setdefault(token, {"seconds": {}})
        prog["step"] = step
        prog["seconds"][step] = round(time.perf_counter() - started, 2)
        if timings is not None:
            prog["timings"] = dict(timings)
        return dict(prog)


def _timed(timings: dict, name: str, fn, *args):
    """Run fn and record its wall time in seconds under `name` (for profiling, no data)."""
    import time

    t = time.perf_counter()
    try:
        return fn(*args)
    finally:
        timings[name] = round(time.perf_counter() - t, 3)


def _warm_routing(routing, a_origin, b_origin, duration_min: int) -> None:
    """Run the two Dijkstra searches while Muse Spark reads the preferences (local engine only),
    bounded like the planner's meetup search."""
    from app.services.planner import MEETUP_TIME_SHARE

    if hasattr(routing, "equal_time_nodes"):
        try:
            routing.matrix([tuple(a_origin), tuple(b_origin)], [tuple(a_origin)],
                           limit_min=duration_min * MEETUP_TIME_SHARE)
        except ProviderError:
            pass  # the planner reports routing problems itself


def run_planning(token: str) -> None:
    """Background, after B accepts. Steps shown on both pages:
    understanding: B's text parsed, wishes read and both Dijkstra runs, in parallel;
    balancing: negotiation (needs B's parsed preference);
    finding: candidates scored with the joint preference, then Muse Spark ranks the top 6;
    done.
    """
    import contextvars
    import time
    from concurrent.futures import ThreadPoolExecutor

    from app.core.config import get_settings, reasoning_override
    from app.providers import get_places, get_routing
    from app.services.explain import rank_candidates
    from app.services.intent import negotiate, parse_intent
    from app.services.planner import plan_for_two
    from app.services.wishes import interpret_wishes

    invite = load_invite(token)
    public, private = load_invite_extra(token)
    if invite is None or private is None or invite.status != "planning":
        return
    started = time.perf_counter()
    reasoning_override.set(get_settings().accept_reasoning_effort)
    a, a_text, b_text = invite.a_intent, private.get("a_text", ""), private.get("b_text", "")
    sources = public.setdefault("sources", {})
    timings: dict[str, float] = {}
    _progress(token, "understanding", started)
    try:
        places, routing = get_places(), get_routing()
        sources["routing"], sources["places"] = routing.name, places.name

        def submit(ex, fn, *args):
            return ex.submit(contextvars.copy_context().run, fn, *args)

        with ThreadPoolExecutor(max_workers=3) as ex:
            f_parse = submit(ex, _timed, timings, "parse_b", parse_intent, b_text) if b_text else None
            f_wishes = (submit(ex, _timed, timings, "wishes", interpret_wishes, a_text, b_text)
                        if (a_text or b_text) else None)
            f_warm = submit(ex, _timed, timings, "routing_search", _warm_routing, routing,
                            private["a_origin"], private["b_origin"], a.duration_min)
            if f_parse:
                parsed = f_parse.result()
                b, sources["b_intent"] = parsed.intent, parsed.source
            else:
                b = WalkIntent(duration_min=a.duration_min)  # B gave no preference: no extra limits
            wishes = f_wishes.result() if f_wishes else None
            if wishes is not None:
                sources["wishes"] = wishes.source
            f_warm.result()
        invite.b_intent = b

        _progress(token, "balancing", started, timings)
        neg = _timed(timings, "negotiate", negotiate, a, b)
        sources["negotiation"] = neg.source

        _progress(token, "finding", started, timings)
        from app.services.nearby import PassBy

        pass_by = [PassBy(**p) for p in public.get("pass_by", [])]
        plan = _timed(timings, "plan", plan_for_two, tuple(private["a_origin"]), tuple(private["b_origin"]),
                      a, b, neg.joint, places, routing, datetime.now(NYC), False, wishes, pass_by)
        ranking = (_timed(timings, "rank", rank_candidates, plan, a, b, neg.joint, wishes)
                   if plan.status == "proposed" else None)
    except ProviderError as e:
        invite.status, invite.error = "error", e.code
        _finish(token, invite, public, private, started, timings)
        return

    public["notes"] = plan.notes
    if ranking is None:
        invite.status, invite.error = "error", plan.status
        public["failure"] = plan.failure.model_dump() if plan.failure else None
    else:
        sources["ranking"] = ranking.source
        invite.status, invite.candidates = "proposed", ranking.candidates
        public.update({"places": {k: v.model_dump(mode="json") for k, v in plan.places.items()},
                       "tradeoff": neg.tradeoff, "reasons": ranking.reasons})
    _finish(token, invite, public, private, started, timings)


def _finish(token: str, invite: Invite, public: dict, private: dict, started: float, timings: dict) -> None:
    """Save the result and the final progress together, then drop the in-memory copy."""
    public["progress"] = _progress(token, "done", started, timings)
    _event(public, "planned")
    save_invite(invite)
    save_invite_extra(token, public, private)
    with _live_lock:
        _live.pop(token, None)
    log.info("invite planned: %s in %.1f s; stages %s", invite.error or invite.status,
             public["progress"]["seconds"]["done"], public["progress"]["timings"])


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
    public, private = load_invite_extra(token)
    if _event(public, "confirmed"):
        save_invite_extra(token, public, private)


ANSWERS = ("yes", "no", "not_sure")


class Feedback(BaseModel):
    """The after-walk survey (DEV_DOC section 9). Stored only with consent; no location."""

    would_have_gone_out: str  # Would you have gone out without the invite?
    fair: str  # Did the meetup point feel fair?
    use_again: str  # Would you use it again?
    actual_walk_min: int | None = None  # optional: how long the walk really took, door to destination


def give_feedback(token: str, key: str | None, consent: bool, answers: Feedback) -> None:
    invite = load_invite(token)
    if invite is None:
        raise InviteError(404, "invite not found")
    role = role_of(token, key)
    if role not in ("a", "b"):
        raise InviteError(403, "only A or B can answer")
    if not consent:
        raise InviteError(400, "answers are stored only with your consent")
    if invite.status != "confirmed":
        raise InviteError(409, "the survey opens once a plan is confirmed")
    if any(v not in ANSWERS for v in (answers.would_have_gone_out, answers.fair, answers.use_again)):
        raise InviteError(400, f"answers must be one of {', '.join(ANSWERS)}")
    if answers.actual_walk_min is not None and not 1 <= answers.actual_walk_min <= 240:
        raise InviteError(400, "actual walk time must be 1-240 minutes")
    c = next(c for c in invite.candidates if c.id == invite.selected_id)
    own = c.a_leg if role == "a" else c.b_leg
    save_feedback(token, role, {
        **answers.model_dump(), "consent": True,
        "predicted_walk_min": round(own.duration_min + c.shared_leg.duration_min, 1),
        "predicted_gap_min": round(c.arrival_gap_min, 1),
    })


class RecapRequest(BaseModel):
    key: str
    minutes_walked: int  # measured by the walker's phone from Start walking to Finish
    place_ids: list[str] = []  # places whose card was shown during the walk


def make_recap(token: str, req: RecapRequest) -> str:
    """A shareable recap of a finished walk: meeting point, destination, the shared leg, minutes
    walked and places passed. Never a start point: the route from each start is left out, and
    so are places within TRIM_M of a start. Returns the recap id."""
    from app.models.db import save_recap

    invite = load_invite(token)
    if invite is None:
        raise InviteError(404, "invite not found")
    role = role_of(token, req.key)
    if role not in ("a", "b"):
        raise InviteError(403, "only A or B can share a recap")
    if invite.status != "confirmed" or not invite.selected_id:
        raise InviteError(409, "a recap needs a confirmed walk")
    if not 1 <= req.minutes_walked <= 300:
        raise InviteError(400, "minutes walked must be 1-300")
    c = next(c for c in invite.candidates if c.id == invite.selected_id)
    public, _ = load_invite_extra(token)
    places = public.get("places", {})
    meet, dest = places.get(c.meeting_place_id, {}), places.get(c.endpoint_place_id, {})
    own = c.a_leg if role == "a" else c.b_leg
    passable = {p["id"]: p for p in own.pois if p.get("along_m", 0) >= TRIM_M}
    passable.update({p["id"]: p for p in c.shared_leg.pois})
    passed = [passable[i] for i in dict.fromkeys(req.place_ids) if i in passable][:30]
    recap_id = secrets.token_urlsafe(9)
    save_recap(recap_id, {
        "date": _now().astimezone(NYC).date().isoformat(),
        "meetup": {"name": meet.get("name"), "lat": meet.get("lat"), "lon": meet.get("lon")},
        "destination": {"name": dest.get("name"), "lat": dest.get("lat"), "lon": dest.get("lon"),
                        "category": dest.get("category")},
        "shared_geometry": c.shared_leg.geometry,
        "shared_min": round(c.shared_leg.duration_min, 1),
        "minutes_walked": req.minutes_walked,
        "places": [{"id": p["id"], "name": p["name"], "category": p["category"]} for p in passed],
        "image_url": public.get("image_url"),
    })
    return recap_id


def get_recap(recap_id: str) -> dict | None:
    from app.models.db import load_recap

    found = load_recap(recap_id)
    if found is None:
        return None
    data, created_at = found
    if datetime.fromisoformat(created_at) < _now() - RECAP_TTL:
        return None
    return {**data, "expires_at": (datetime.fromisoformat(created_at) + RECAP_TTL).isoformat()}
