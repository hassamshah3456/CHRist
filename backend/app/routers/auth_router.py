"""Registration, sign-in, MFA, session management and collector presence.

Every authentication outcome — success, failure, lockout, MFA failure, logout —
is written to the PHI audit trail. Failed sign-ins matter as much as successful
ones: a burst of them is the earliest signal of a credential attack on an
account that can reach participant data.
"""
import os
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import audit, models, schemas
from ..audit import Action
from ..auth import (
    admin_mfa_required,
    consume_recovery_code,
    create_access_token,
    enforce_password_policy,
    generate_recovery_codes,
    get_current_user,
    hash_password,
    lock_remaining,
    mfa_provisioning_uri,
    new_mfa_secret,
    register_failed_login,
    register_successful_login,
    revoke_all_sessions,
    verify_password,
    verify_totp,
)
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

# The MFA ticket is a separate, deliberately short-lived JWT. It proves the
# password step succeeded and nothing more — get_current_user will not accept
# it, because it carries a distinct purpose claim.
MFA_TICKET_MINUTES = 5
MFA_TICKET_PURPOSE = "mfa-pending"


def _normalize_phone(raw: str) -> str:
    """Keep digits only so 98765 43210 and +91-9876543210 match."""
    return re.sub(r"\D", "", (raw or "").strip())


def _issue_mfa_ticket(user: models.User) -> str:
    return jwt.encode(
        {
            "sub": user.id,
            "purpose": MFA_TICKET_PURPOSE,
            "exp": datetime.utcnow() + timedelta(minutes=MFA_TICKET_MINUTES),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _redeem_mfa_ticket(db: Session, ticket: str) -> models.User:
    try:
        payload = jwt.decode(
            ticket, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This sign-in attempt expired. Please start again.",
        )
    if payload.get("purpose") != MFA_TICKET_PURPOSE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ticket."
        )
    user = db.query(models.User).filter(
        models.User.id == payload.get("sub")
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ticket."
        )
    return user


def _token_response(user: models.User) -> schemas.TokenResponse:
    return schemas.TokenResponse(
        access_token=create_access_token(user),
        user=user,
        idle_lock_minutes=settings.IDLE_LOCK_MINUTES,
    )


# ------------------------------------------------------------------ register
@router.post("/register", response_model=schemas.TokenResponse)
def register(
    payload: schemas.RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    phone = _normalize_phone(payload.phone)
    if len(phone) < 7:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter a valid phone number.",
        )

    # Complexity policy runs before anything is written.
    enforce_password_policy(payload.password)

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
        password_changed_at=datetime.utcnow(),
        upi_address=(payload.upi_address or "").strip() or "-",
        upi_name=payload.upi_name,
        signup_lat=loc.lat if loc else None,
        signup_lng=loc.lng if loc else None,
        signup_address=loc.address if loc else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    audit.record_user(
        user, Action.LOGIN_SUCCESS, request=request,
        resource_type="account", resource_id=user.id, subject_count=0,
        detail="account created",
    )
    return _token_response(user)


# --------------------------------------------------------------------- login
@router.post("/login")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Password step. Collectors receive a token directly; admins with MFA
    required receive a challenge instead.

    The response model is intentionally unannotated because this endpoint
    returns either a TokenResponse or an MfaChallengeResponse.
    """
    username = (form.username or "").strip()
    phone = _normalize_phone(username)
    user = db.query(models.User).filter(
        or_(
            models.User.phone == phone,
            func.lower(models.User.email) == username.lower(),
        )
    ).first()

    # Unknown account: audit the attempt, then fail with the same generic
    # message used for a wrong password, so responses cannot be used to
    # enumerate who holds an account.
    if not user:
        audit.record(
            actor_id=None, actor_name=username[:255],
            action=Action.LOGIN_FAILURE, request=request, success=False,
            subject_count=0, detail="no such account",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email, phone, or password.",
        )

    remaining = lock_remaining(user)
    if remaining:
        minutes = max(1, int(remaining.total_seconds() // 60) + 1)
        audit.record_user(
            user, Action.LOGIN_LOCKED, request=request, success=False,
            subject_count=0, detail=f"locked, {minutes} min remaining",
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Too many failed attempts. Try again in {minutes} minute"
                   f"{'s' if minutes != 1 else ''}.",
        )

    if not verify_password(form.password, user.password_hash):
        locked = register_failed_login(db, user)
        audit.record_user(
            user,
            Action.LOGIN_LOCKED if locked else Action.LOGIN_FAILURE,
            request=request, success=False, subject_count=0,
            detail="lockout triggered" if locked else "wrong password",
        )
        if locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Too many failed attempts. This account is locked for "
                       f"{settings.LOCKOUT_MINUTES} minutes.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email, phone, or password.",
        )

    register_successful_login(db, user)

    # Admins must clear a second factor before a usable token is issued.
    if admin_mfa_required(user):
        return schemas.MfaChallengeResponse(
            mfa_ticket=_issue_mfa_ticket(user),
            enrollment_required=not user.mfa_enabled,
        )

    audit.record_user(
        user, Action.LOGIN_SUCCESS, request=request,
        resource_type="account", resource_id=user.id, subject_count=0,
    )
    return _token_response(user)


@router.post("/login/mfa", response_model=schemas.TokenResponse)
def login_mfa(
    payload: schemas.MfaVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Second step: exchange a ticket plus a TOTP or recovery code for a token."""
    user = _redeem_mfa_ticket(db, payload.mfa_ticket)

    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multi-factor authentication is not set up on this account.",
        )

    code = (payload.code or "").strip()
    ok = verify_totp(user.mfa_secret, code) or consume_recovery_code(db, user, code)
    if not ok:
        locked = register_failed_login(db, user)
        audit.record_user(
            user, Action.MFA_FAILURE, request=request, success=False,
            subject_count=0,
            detail="lockout triggered" if locked else "wrong code",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That code is not valid.",
        )

    register_successful_login(db, user)
    audit.record_user(
        user, Action.LOGIN_SUCCESS, request=request,
        resource_type="account", resource_id=user.id, subject_count=0,
        detail="second factor verified",
    )
    return _token_response(user)


# ----------------------------------------------------------------------- MFA
@router.post("/mfa/enroll", response_model=schemas.MfaEnrollResponse)
def mfa_enroll(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Generate a fresh TOTP secret and recovery codes.

    The secret is stored immediately but `mfa_enabled` stays false until a
    valid code reaches /auth/mfa/activate — otherwise a mistyped setup would
    lock an administrator out of their own dashboard.
    """
    secret = new_mfa_secret()
    codes, hashes = generate_recovery_codes()
    user.mfa_secret = secret
    user.mfa_recovery_hashes = hashes
    user.mfa_enabled = False
    db.commit()
    return schemas.MfaEnrollResponse(
        secret=secret,
        otpauth_url=mfa_provisioning_uri(user, secret),
        recovery_codes=codes,
    )


@router.post("/mfa/activate", response_model=schemas.SimpleMessage)
def mfa_activate(
    payload: schemas.MfaActivateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Confirm enrolment by proving the authenticator produces valid codes."""
    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start enrolment first.",
        )
    if not verify_totp(user.mfa_secret, payload.code):
        audit.record_user(
            user, Action.MFA_FAILURE, request=request, success=False,
            subject_count=0, detail="activation code rejected",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code is not valid. Check your authenticator app.",
        )
    user.mfa_enabled = True
    db.commit()
    audit.record_user(
        user, Action.MFA_ENROLLED, request=request,
        resource_type="account", resource_id=user.id, subject_count=0,
    )
    return schemas.SimpleMessage(detail="Multi-factor authentication is on.")


# ------------------------------------------------------------------ sessions
@router.post("/logout", response_model=schemas.SimpleMessage)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Sign out everywhere by invalidating every token for this account."""
    revoke_all_sessions(db, user)
    audit.record_user(
        user, Action.LOGOUT, request=request,
        resource_type="account", resource_id=user.id, subject_count=0,
    )
    return schemas.SimpleMessage(detail="Signed out on all devices.")


@router.post("/change-password", response_model=schemas.SimpleMessage)
def change_password(
    payload: schemas.ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, user.password_hash):
        audit.record_user(
            user, Action.LOGIN_FAILURE, request=request, success=False,
            subject_count=0, detail="wrong current password on change",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your current password is not correct.",
        )
    enforce_password_policy(payload.new_password)

    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.utcnow()
    db.commit()
    # Changing a password signs out every other device, which is what someone
    # who suspects compromise expects it to do.
    revoke_all_sessions(db, user)
    return schemas.SimpleMessage(
        detail="Password changed. Please sign in again on your other devices."
    )


# ------------------------------------------------------------------ presence
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
    worked offline is counted once connectivity returns. The delta is bounded
    by the schema, and the device caps each interval so suspended time isn't
    sent.

    Deliberately not audited: a heartbeat every 30 seconds per collector would
    bury genuine PHI access in noise, and it exposes no participant data.
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


# ------------------------------------------------------------------- account
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
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Delete the signed-in collector account (Google Play account-deletion policy).

    Removes the collector profile, submissions, payouts, and uploaded photos.
    Admin accounts cannot self-delete via this endpoint.

    The audit row is written BEFORE the deletion and deliberately outlives the
    account: destruction of participant records is exactly the event a later
    investigation needs to see, which is why the audit table holds no foreign
    key back to users.
    """
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts cannot be deleted from the app.",
        )

    collections = db.query(models.Collection).filter(
        models.Collection.user_id == user.id
    ).all()

    audit.record_user(
        user, Action.DELETE_ACCOUNT, request=request,
        resource_type="account", resource_id=user.id,
        subject_count=len(collections),
        detail=f"account deletion removed {len(collections)} participant records",
    )

    _delete_media_files(collections)
    for c in collections:
        db.delete(c)
    db.query(models.Payout).filter(models.Payout.user_id == user.id).delete()
    user.groups.clear()
    db.delete(user)
    db.commit()
