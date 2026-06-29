"""Registration, login, and collector presence endpoints."""
import os
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_phone(raw: str) -> str:
    """Keep digits only so 98765 43210 and +91-9876543210 match."""
    return re.sub(r"\D", "", (raw or "").strip())


@router.post("/register", response_model=schemas.TokenResponse)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    phone = _normalize_phone(payload.phone)
    if len(phone) < 7:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter a valid phone number.",
        )

    existing = db.query(models.User).filter(models.User.phone == phone).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this phone number already exists.",
        )

    loc = payload.signup_location
    user = models.User(
        name=payload.name,
        phone=phone,
        email=None,
        password_hash=hash_password(payload.password),
        upi_address=(payload.upi_address or "").strip() or "-",
        upi_name=payload.upi_name,
        signup_lat=loc.lat if loc else None,
        signup_lng=loc.lng if loc else None,
        signup_address=loc.address if loc else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return schemas.TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=schemas.TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # OAuth2PasswordRequestForm uses `username` — collectors may pass phone or
    # email (legacy accounts registered with email).
    username = (form.username or "").strip()
    phone = _normalize_phone(username)
    user = db.query(models.User).filter(
        or_(
            models.User.phone == phone,
            func.lower(models.User.email) == username.lower(),
        )
    ).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email, phone, or password.",
        )

    token = create_access_token(user.id)
    return schemas.TokenResponse(access_token=token, user=user)


@router.post("/heartbeat", response_model=schemas.HeartbeatResponse)
def heartbeat(
    payload: schemas.HeartbeatRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Record foreground app activity and the collector's latest location.

    Heartbeats are sent about every 30 seconds. Time worked is client-driven:
    the app accrues real foreground seconds locally (even offline) and reports
    the increment in ``app_seconds_delta``; we simply add it. This means time
    worked offline is counted once connectivity returns. The delta is bounded by
    the schema, and the device caps each interval so suspended time isn't sent.
    """
    now = datetime.utcnow()
    delta = max(0, int(payload.app_seconds_delta or 0))
    if delta:
        user.app_seconds = (user.app_seconds or 0) + delta

    user.active_session_id = payload.session_id
    user.last_seen = now
    loc = payload.location
    if loc:
        if loc.lat is not None:
            user.last_lat = loc.lat
        if loc.lng is not None:
            user.last_lng = loc.lng
        if loc.address:
            user.last_address = loc.address

    db.commit()
    db.refresh(user)
    return schemas.HeartbeatResponse(
        last_seen=user.last_seen,
        app_seconds=user.app_seconds or 0,
    )


def _delete_media_files(collections) -> None:
    """Remove uploaded photos from disk when a collector account is deleted."""
    names = set()
    for c in collections:
        if c.medical_record_photo:
            names.add(c.medical_record_photo)
        for a in c.answers:
            if a.photo_filename:
                names.add(a.photo_filename)
    for name in names:
        path = os.path.join(settings.MEDIA_DIR, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass


@router.delete("/account", status_code=204)
def delete_account(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Delete the signed-in collector account (Google Play account-deletion policy).

    Removes the collector profile, submissions, payouts, and uploaded photos.
    Admin accounts cannot self-delete via this endpoint.
    """
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts cannot be deleted from the app.",
        )

    collections = db.query(models.Collection).filter(
        models.Collection.user_id == user.id
    ).all()
    _delete_media_files(collections)

    for c in collections:
        db.delete(c)
    db.query(models.Payout).filter(models.Payout.user_id == user.id).delete()
    user.groups.clear()
    db.delete(user)
    db.commit()
