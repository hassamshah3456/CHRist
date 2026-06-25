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

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Collections ----------
class CollectionIn(BaseModel):
    """One collection coming up from the device (offline-capable)."""
    id: Optional[str] = None  # client UUID; server keeps it for idempotency
    verbal_consent: bool = False
    child_age: Optional[int] = None
    child_sex: Optional[str] = None
    responder: Optional[str] = None
    responder_other: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_address: Optional[str] = None
    collected_at: Optional[datetime] = None


class CollectionOut(BaseModel):
    id: str
    collector_name: str
    verbal_consent: bool
    child_age: Optional[int] = None
    child_sex: Optional[str] = None
    responder: Optional[str] = None
    responder_other: Optional[str] = None
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
