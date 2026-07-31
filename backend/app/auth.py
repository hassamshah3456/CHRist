"""Password hashing, JWT creation, MFA, lockout, and the current-user dependency.

Security properties enforced here:

* Passwords are bcrypt-hashed and must meet a complexity policy
  (§164.308(a)(5)(ii)(D)).
* Every JWT carries the account's `token_version`; bumping that column revokes
  all outstanding sessions instantly — the missing piece behind "sign out
  everywhere" and offboarding (§164.308(a)(3)(ii)(C)).
* Admin sessions expire in an hour; collector sessions last days because field
  work is offline, with the automatic-logoff safeguard met on the device by an
  inactivity lock (§164.312(a)(2)(iii)).
* Repeated failures lock the account for a cooling-off period, and every
  attempt — successful or not — is auditable.
* Admin accounts require a TOTP second factor in production.
"""
import re
import secrets
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pyotp
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

RECOVERY_CODE_COUNT = 8


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def password_problems(password: str) -> List[str]:
    """Return human-readable reasons a password is unacceptable.

    Deliberately not a wall of regexes: length does most of the real work, and
    the character-class rules exist because they are what auditors look for.
    """
    problems = []
    if len(password or "") < settings.MIN_PASSWORD_LENGTH:
        problems.append(
            f"be at least {settings.MIN_PASSWORD_LENGTH} characters long"
        )
    if not re.search(r"[A-Za-z]", password or ""):
        problems.append("contain a letter")
    if not re.search(r"\d", password or ""):
        problems.append("contain a digit")
    if (password or "").lower() in {
        "password", "password1", "12345678", "qwertyuiop",
        "letmein123", "changeme1", "welcome123",
    }:
        problems.append("not be a commonly used password")
    return problems


def enforce_password_policy(password: str) -> None:
    problems = password_problems(password)
    if problems:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must " + ", and ".join(problems) + ".",
        )


# ------------------------------------------------------------------- tokens
def token_lifetime(user: User) -> timedelta:
    """Admins get a short session; collectors need to survive offline days."""
    minutes = (
        settings.ADMIN_TOKEN_EXPIRE_MINUTES
        if user.is_admin
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return timedelta(minutes=minutes)


def create_access_token(user: User) -> str:
    """Mint a JWT bound to the account's current token version.

    Takes the User rather than a bare id so the version and role travel with
    the token and cannot drift out of sync.
    """
    now = datetime.utcnow()
    payload = {
        "sub": user.id,
        "ver": int(user.token_version or 0),
        "adm": bool(user.is_admin),
        "exp": now + token_lifetime(user),
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def revoke_all_sessions(db: Session, user: User) -> None:
    """Invalidate every outstanding token for this account."""
    user.token_version = int(user.token_version or 0) + 1
    db.commit()


# -------------------------------------------------------------- account lock
def lock_remaining(user: User) -> Optional[timedelta]:
    """Time left on an active lockout, or None if the account is usable."""
    if user.locked_until and user.locked_until > datetime.utcnow():
        return user.locked_until - datetime.utcnow()
    return None


def register_failed_login(db: Session, user: User) -> bool:
    """Count a failed attempt; lock the account past the threshold.

    Returns True if this failure triggered a lockout.
    """
    user.failed_login_count = int(user.failed_login_count or 0) + 1
    locked = False
    if user.failed_login_count >= settings.MAX_LOGIN_ATTEMPTS:
        user.locked_until = datetime.utcnow() + timedelta(
            minutes=settings.LOCKOUT_MINUTES
        )
        user.failed_login_count = 0
        locked = True
    db.commit()
    return locked


def register_successful_login(db: Session, user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()


# ----------------------------------------------------------------------- MFA
def new_mfa_secret() -> str:
    return pyotp.random_base32()


def mfa_provisioning_uri(user: User, secret: str) -> str:
    """otpauth:// URI that an authenticator app renders as a QR code."""
    label = user.email or user.phone or user.name
    return pyotp.TOTP(secret).provisioning_uri(
        name=label, issuer_name=settings.MFA_ISSUER
    )


def verify_totp(secret: str, code: str) -> bool:
    """Validate a 6-digit code, tolerating one step of clock drift."""
    if not secret or not code:
        return False
    cleaned = str(code).strip().replace(" ", "")
    return pyotp.TOTP(secret).verify(cleaned, valid_window=1)


def generate_recovery_codes() -> Tuple[List[str], str]:
    """Fresh recovery codes: plaintext to show once, and hashes to store."""
    codes = [
        f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}"
        for _ in range(RECOVERY_CODE_COUNT)
    ]
    return codes, "\n".join(hash_password(c) for c in codes)


def consume_recovery_code(db: Session, user: User, code: str) -> bool:
    """Spend a single-use recovery code, removing it on success."""
    stored = (user.mfa_recovery_hashes or "").splitlines()
    cleaned = (code or "").strip().lower()
    if not cleaned:
        return False
    for h in stored:
        if h and verify_password(cleaned, h):
            user.mfa_recovery_hashes = "\n".join(x for x in stored if x != h)
            db.commit()
            return True
    return False


def admin_mfa_required(user: User) -> bool:
    """Whether this admin must present a second factor to obtain a token."""
    return bool(user.is_admin and settings.REQUIRE_ADMIN_MFA)


# --------------------------------------------------------------- dependencies
_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError:
        raise _credentials_exc

    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise _credentials_exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise _credentials_exc

    # Reject tokens minted before the last revocation. Tokens issued before
    # this field existed carry no "ver" claim; treat those as version 0 so
    # sessions from the previous build keep working until first revocation.
    if int(payload.get("ver", 0) or 0) != int(user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been signed out. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if lock_remaining(user):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="This account is temporarily locked.",
        )

    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Like get_current_user but rejects non-admin accounts (web dashboard)."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    if admin_mfa_required(user) and not user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Multi-factor authentication must be enabled on this "
                   "account before administrative data can be accessed.",
        )
    return user
