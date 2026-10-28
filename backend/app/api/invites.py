"""Invite endpoints (DEV_DOC section 7). Accepting starts planning; there is no separate plan call."""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response
from pydantic import BaseModel, Field

from app.models.schemas import WalkIntent
from app.services import invites
from app.services.invite_card import card_path

router = APIRouter(prefix="/api/invites", tags=["invites"])


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class CreateInviteRequest(BaseModel):
    a_intent: WalkIntent
    a_origin: LatLon
    a_text: str = Field(default="", max_length=500)


class CreateInviteResponse(BaseModel):
    token: str
    invite_path: str
    a_key: str  # A's private key: polling with it shows A's own full leg; never share it
    expires_at: datetime
    view: invites.InviteView


class AcceptRequest(BaseModel):
    b_origin: LatLon
    b_text: str = Field(default="", max_length=500)


class AcceptResponse(BaseModel):
    b_key: str
    view: invites.InviteView


class ConfirmRequest(BaseModel):
    key: str
    candidate_id: str | None = None  # default: the top candidate


def _raise(e: invites.InviteError):
    raise HTTPException(status_code=e.status, detail=e.message)


@router.post("", status_code=201)
def create_invite(req: CreateInviteRequest, background: BackgroundTasks) -> CreateInviteResponse:
    invite, a_key = invites.create(req.a_intent, (req.a_origin.lat, req.a_origin.lon), req.a_text)
    background.add_task(invites.make_image, invite.token)
    return CreateInviteResponse(token=invite.token, invite_path=f"/i/{invite.token}", a_key=a_key,
                                expires_at=invite.expires_at, view=invites.view(invite.token, a_key))


@router.get("/{token}")
def get_invite(token: str, key: str | None = None) -> invites.InviteView:
    v = invites.view(token, key)
    if v is None:
        raise HTTPException(status_code=404, detail="invite not found")
    return v


@router.post("/{token}/accept")
def accept_invite(token: str, req: AcceptRequest, background: BackgroundTasks) -> AcceptResponse:
    try:
        b_key = invites.accept(token, (req.b_origin.lat, req.b_origin.lon), req.b_text)
    except invites.InviteError as e:
        _raise(e)
    background.add_task(invites.run_planning, token)
    return AcceptResponse(b_key=b_key, view=invites.view(token, b_key))


@router.post("/{token}/confirm")
def confirm_invite(token: str, req: ConfirmRequest) -> invites.InviteView:
    try:
        invites.confirm(token, req.key, req.candidate_id)
    except invites.InviteError as e:
        _raise(e)
    return invites.view(token, req.key)


@router.get("/{token}/card")
def invite_card(token: str) -> Response:
    path = card_path(token)
    if path is None:
        raise HTTPException(status_code=404, detail="no card image")
    media = {"webp": "image/webp", "png": "image/png", "jpg": "image/jpeg"}[path.suffix[1:]]
    return Response(content=path.read_bytes(), media_type=media, headers={"Cache-Control": "max-age=3600"})
