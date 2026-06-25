"""Pydantic request/response schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ---------- Auth ----------
class GeoPoint(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: Optional[str] = None


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)
    upi_address: str = Field(..., min_length=1)
    upi_name: Optional[str] = None
    signup_location: Optional[GeoPoint] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    upi_address: str
    upi_name: Optional[str] = None
    is_admin: bool = False

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Questionnaire ----------
QTYPES = {"yes_no", "single_choice", "multi_choice", "number", "text"}


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
    email: EmailStr
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


class AdminStats(BaseModel):
    total: int
    today: int
    this_week: int
    this_month: int
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
    vaccines: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_address: Optional[str] = None
    collected_at: datetime
    answers: List[AnswerOut] = []


# ---------- Payments ----------
class PaymentConfig(BaseModel):
    """Admin-configurable payout rates (currency is informational)."""
    per_entry: float = 0
    training: float = 0
    currency: str = "₹"


class PayoutOut(BaseModel):
    amount: float
    entries_count: int
    per_entry: float
    training_included: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CollectorPayment(BaseModel):
    """Per-collector payout status for the admin Payments table."""
    id: str
    name: str
    email: EmailStr
    upi_address: str
    upi_name: Optional[str] = None
    total_entries: int
    unpaid_entries: int
    per_entry: float
    training: float
    training_paid: bool
    due: float                  # unpaid_entries*per_entry (+ training if unpaid)
    currency: str = "₹"
    last_payout: Optional[PayoutOut] = None


class PaymentsOverview(BaseModel):
    config: PaymentConfig
    collectors: List[CollectorPayment]


class MyPayment(BaseModel):
    """Payment summary shown to a collector in the app."""
    currency: str = "₹"
    per_entry: float
    training: float
    total_entries: int
    unpaid_entries: int
    due: float
    training_paid: bool
    last_payout: Optional[PayoutOut] = None
