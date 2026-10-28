"""Invite endpoints. Day 1 stub: create and store only; accept/plan come later."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.models.db import save_invite
from app.models.schemas import Invite, WalkIntent

router = APIRouter(prefix="/api/invites", tags=["invites"])

INVITE_TTL = timedelta(hours=24)


class CreateInviteRequest(BaseModel):
    a_intent: WalkIntent


class CreateInviteResponse(BaseModel):
    token: str
    invite_path: str
    expires_at: datetime
    invite: Invite


def template_invite_text(intent: WalkIntent) -> str:
    # Template fallback; the Muse Spark invite text replaces it later.
    text = f"Up for a {intent.duration_min}-minute walk together?"
    if intent.endpoint_type:
        text += f" It ends at a {intent.endpoint_type}."
    return text


@router.post("", status_code=201)
def create_invite(req: CreateInviteRequest) -> CreateInviteResponse:
    invite = Invite(
        token=secrets.token_urlsafe(16),
        status="pending",
        expires_at=datetime.now(timezone.utc) + INVITE_TTL,
        invite_text=template_invite_text(req.a_intent),
        a_intent=req.a_intent,
    )
    save_invite(invite)
    return CreateInviteResponse(
        token=invite.token,
        invite_path=f"/i/{invite.token}",
        expires_at=invite.expires_at,
        invite=invite,
    )
