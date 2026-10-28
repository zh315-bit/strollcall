from datetime import datetime

from pydantic import BaseModel, Field

# --- DEV_DOC section 7 ---


class WalkIntent(BaseModel):
    duration_min: int = Field(ge=15, le=60)
    duration_strict: bool = False  # a hard limit ("only", "must", "at most"): no time tolerance
    vibes: list[str] = []
    endpoint_type: str | None = None
    avoid: list[str] = []
    hard_constraints: list[str] = []


class JointPreference(BaseModel):
    shared_vibes: list[str]
    a_priorities: list[str]
    b_priorities: list[str]
    compromises: list[str]


class RouteLeg(BaseModel):
    geometry: list[tuple[float, float]]  # (lat, lon) points, Leaflet order
    distance_m: float
    duration_min: float


class MeetupCandidate(BaseModel):
    id: str
    meeting_place_id: str
    endpoint_place_id: str
    a_leg: RouteLeg
    b_leg: RouteLeg
    shared_leg: RouteLeg
    arrival_gap_min: float
    total_elapsed_min: float
    score: float
    rationale: str


class Invite(BaseModel):
    token: str
    status: str  # pending / planning / proposed / confirmed / expired
    expires_at: datetime
    invite_text: str
    a_intent: WalkIntent
    b_intent: WalkIntent | None = None
    candidates: list[MeetupCandidate] = []
    selected_id: str | None = None
    error: str | None = None


# --- Provider data ---


class Place(BaseModel):
    id: str  # OSM id, e.g. "node/123"
    name: str
    lat: float
    lon: float
    # destinations: cafe / bookstore / park / bakery / ice_cream / landmark
    # meetup points: park / park_gate / subway_entrance / plaza / landmark
    category: str
    opening_hours: str | None = None  # raw OSM opening_hours; None = unknown
    tags: dict[str, str] = {}  # selected OSM tags, for preference fit
    fetched_at: datetime | None = None  # when the OSM data was read; hours are "as of" this


class TravelMatrix(BaseModel):
    # [source][destination]; None when no walking route was found
    durations_min: list[list[float | None]]
    distances_m: list[list[float | None]]
