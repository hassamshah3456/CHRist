"""Pydantic request/response schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


# ---------- Auth ----------
class GeoPoint(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: Optional[str] = None


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=7, max_length=32)
    password: str = Field(..., min_length=6)
    # Optional: a collector may use a relative's UPI, or none at all.
    upi_address: str = ""
    upi_name: Optional[str] = None
    signup_location: Optional[GeoPoint] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    upi_address: str
    upi_name: Optional[str] = None
    is_admin: bool = False

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Presence ----------
class HeartbeatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=36)
    location: Optional[GeoPoint] = None


class HeartbeatResponse(BaseModel):
    online: bool = True
    last_seen: datetime
    app_seconds: int


# ---------- Questionnaire ----------
QTYPES = {"yes_no", "single_choice", "multi_choice", "number", "text"}


class FollowUp(BaseModel):
    """A nested question asked only when its parent yes/no is answered "Yes".

    Mirrors the main question shape so it supports the same yes/no and upload
    (photo on "Yes") functionality, plus the other answer types."""
    title: str = ""
    help_text: Optional[str] = None
    qtype: str = "yes_no"
    options: List[str] = []
    required: bool = False
    photo_on_yes: bool = False
    note_on_yes: bool = False
    translations: Dict[str, Any] = {}


class QuestionIn(BaseModel):
    code: Optional[str] = None  # auto-generated if omitted
    title: str = Field(..., min_length=1)
    help_text: Optional[str] = None
    qtype: str = "yes_no"
    options: List[str] = []
    required: bool = True
    secondary_aim: bool = False
    photo_on_yes: bool = False
    note_on_yes: bool = False
    is_active: bool = True
    order_index: Optional[int] = None
    # Per-language overrides, e.g. {"hi": {"title": "...", "help_text": "...",
    # "options": [...]}, "kn": {...}}. English uses the base fields above.
    translations: Dict[str, Any] = {}
    # Optional follow-up shown when this yes/no question is answered "Yes".
    follow_up: Optional[FollowUp] = None


class QuestionOut(BaseModel):
    id: str
    code: str
    order_index: int
    title: str
    help_text: Optional[str] = None
    qtype: str
    options: List[str] = []
    required: bool
    secondary_aim: bool
    photo_on_yes: bool
    note_on_yes: bool
    is_active: bool
    translations: Dict[str, Any] = {}
    follow_up: Optional[FollowUp] = None


class ReorderRequest(BaseModel):
    ordered_ids: List[str]


# ---------- Answers ----------
class AnswerIn(BaseModel):
    question_id: Optional[str] = None
    question_code: str
    question_title: Optional[str] = None
    qtype: Optional[str] = None
    value_bool: Optional[bool] = None
    value_number: Optional[float] = None
    value_text: Optional[str] = None
    photo_filename: Optional[str] = None


class AnswerOut(BaseModel):
    question_code: str
    question_title: Optional[str] = None
    qtype: Optional[str] = None
    value_bool: Optional[bool] = None
    value_number: Optional[float] = None
    value_text: Optional[str] = None
    photo_filename: Optional[str] = None


# ---------- Collections ----------
class CollectionIn(BaseModel):
    """One collection coming up from the device (offline-capable)."""
    id: Optional[str] = None  # client UUID; server keeps it for idempotency
    verbal_consent: bool = False
    phone: Optional[str] = None
    child_name: Optional[str] = None
    child_age: Optional[int] = None
    child_age_months: Optional[int] = None
    child_sex: Optional[str] = None
    responder: Optional[str] = None
    responder_other: Optional[str] = None
    medical_record: Optional[bool] = None
    medical_record_photo: Optional[str] = None
    card_submitted: bool = False
    vaccines: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_address: Optional[str] = None
    collected_at: Optional[datetime] = None
    answers: List[AnswerIn] = []


class CollectionOut(BaseModel):
    id: str
    collector_name: str
    verbal_consent: bool
    child_name: Optional[str] = None
    child_age: Optional[int] = None
    child_age_months: Optional[int] = None
    child_sex: Optional[str] = None
    responder: Optional[str] = None
    responder_other: Optional[str] = None
    medical_record: Optional[bool] = None
    medical_record_photo: Optional[str] = None
    card_submitted: bool = False
    card_approved: bool = False
    vaccines: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_address: Optional[str] = None
    collected_at: datetime

    class Config:
        from_attributes = True


class SyncRequest(BaseModel):
    """Batch upload of pending collections from the device."""
    collections: List[CollectionIn] = []


class SyncResponse(BaseModel):
    synced_ids: List[str]


# ---------- Stats ----------
class StatsResponse(BaseModel):
    total: int
    today: int
    this_week: int
    this_month: int
    consent_yes: int
    consent_no: int


# ---------- Admin dashboard ----------
class DailyPoint(BaseModel):
    date: str   # YYYY-MM-DD
    count: int


class BreakdownItem(BaseModel):
    label: str
    count: int


class QuestionStat(BaseModel):
    """Aggregated Yes/No positivity for one screening question (e.g. vaccine
    coverage) across all collected answers."""
    code: str
    label: str
    yes: int
    no: int
    total: int


class CollectorSummary(BaseModel):
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    upi_address: str
    upi_name: Optional[str] = None
    total: int
    last_collection: Optional[datetime] = None
    signup_lat: Optional[float] = None
    signup_lng: Optional[float] = None
    signup_address: Optional[str] = None
    # Live presence (from the app heartbeat)
    online: bool = False
    last_seen: Optional[datetime] = None
    last_lat: Optional[float] = None
    last_lng: Optional[float] = None
    last_address: Optional[str] = None
    app_seconds: int = 0


class CollectorGroupIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    member_ids: List[str] = []


class CollectorGroupSummary(BaseModel):
    id: str
    name: str
    members_count: int
    collections_count: int
    online_count: int
    created_at: datetime


class CollectorGroupDetail(BaseModel):
    id: str
    name: str
    members_count: int
    collections_count: int
    online_count: int
    created_at: datetime
    members: List[CollectorSummary]


class AdminStats(BaseModel):
    total: int
    today: int
    this_week: int
    this_month: int
    triple_positive: int = 0  # submissions with 3+ Yes (includes quadruple)
    positivity_normal: int = 0   # < 3 Yes
    positivity_triple: int = 0   # exactly 3 Yes (subset of triple_positive)
    positivity_quadruple: int = 0  # 4+ Yes (included in triple_positive)
    consent_yes: int
    consent_no: int
    collectors_count: int
    avg_age: Optional[float] = None       # mean child age in years
    daily: List[DailyPoint]               # last 30 days
    sex_breakdown: List[BreakdownItem]
    responder_breakdown: List[BreakdownItem]
    age_breakdown: List[BreakdownItem] = []        # by age band
    question_stats: List[QuestionStat] = []        # Yes/No positivity per question
    collectors: List[CollectorSummary]


class AdminCollectionOut(BaseModel):
    id: str
    user_id: str
    collector_name: str
    collector_email: Optional[str] = None
    collector_phone: Optional[str] = None
    verbal_consent: bool
    phone: Optional[str] = None
    child_name: Optional[str] = None
    child_age: Optional[int] = None
    child_age_months: Optional[int] = None
    child_sex: Optional[str] = None
    responder: Optional[str] = None
    responder_other: Optional[str] = None
    medical_record: Optional[bool] = None
    medical_record_photo: Optional[str] = None
    card_submitted: bool = False
    card_approved: bool = False
    vaccines: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_address: Optional[str] = None
    collected_at: datetime
    answers: List[AnswerOut] = []


class AdminCollectionsPage(BaseModel):
    items: List[AdminCollectionOut]
    total: int
    page: int
    page_size: int
    pages: int


class CollectionMapPoint(BaseModel):
    id: str
    child_name: Optional[str] = None
    collector_name: str
    child_age: Optional[int] = None
    child_age_months: Optional[int] = None
    verbal_consent: bool
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    collected_at: datetime


# ---------- Payments ----------
class Instructions(BaseModel):
    """Single-language instructions returned to the app."""
    html: str = ""


class InstructionsMulti(BaseModel):
    """Per-language instructions, edited in the admin dashboard."""
    en: str = ""
    hi: str = ""
    kn: str = ""


class PaymentConfig(BaseModel):
    """Admin-configurable payout rates (currency is informational)."""
    per_entry: float = 0
    card_entry: float = 0
    training: float = 0
    currency: str = "₹"


class PayoutOut(BaseModel):
    amount: float
    entries_count: int
    per_entry: float
    card_entries_count: int = 0
    card_per_entry: float = 0
    training_included: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CollectorPayment(BaseModel):
    """Per-collector payout status for the admin Payments table."""
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    upi_address: str
    upi_name: Optional[str] = None
    total_entries: int
    unpaid_entries: int
    regular_unpaid_entries: int = 0
    card_entries: int = 0
    approved_card_entries: int = 0
    approved_card_unpaid_entries: int = 0
    pending_card_entries: int = 0
    per_entry: float
    card_entry: float
    training: float
    training_paid: bool
    due: float                  # unpaid_entries*per_entry (+ training if unpaid)
    currency: str = "₹"
    last_payout: Optional[PayoutOut] = None


class PaymentsOverview(BaseModel):
    config: PaymentConfig
    collectors: List[CollectorPayment]
    total_due: float = 0
    total_paid: float = 0


class MyPayment(BaseModel):
    """Payment summary shown to a collector in the app."""
    currency: str = "₹"
    per_entry: float
    card_entry: float
    training: float
    total_entries: int
    unpaid_entries: int
    regular_unpaid_entries: int = 0
    card_entries: int = 0
    approved_card_entries: int = 0
    approved_card_unpaid_entries: int = 0
    pending_card_entries: int = 0
    due: float
    training_paid: bool
    last_payout: Optional[PayoutOut] = None
