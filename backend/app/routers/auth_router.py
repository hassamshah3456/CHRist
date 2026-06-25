"""Registration and login endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import create_access_token, hash_password, verify_password
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenResponse)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(
        models.User.email == payload.email
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    loc = payload.signup_location
    user = models.User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        upi_address=payload.upi_address,
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
    # OAuth2PasswordRequestForm uses `username`; we treat it as the email.
    user = db.query(models.User).filter(
        models.User.email == form.username
    ).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    token = create_access_token(user.id)
    return schemas.TokenResponse(access_token=token, user=user)
