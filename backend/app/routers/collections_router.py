"""Collection sync + listing endpoints (all require auth)."""
import os
import uuid as uuidlib
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/collections", tags=["collections"])

_ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 8 MB


def _range_start(period: str) -> Optional[datetime]:
    """Return the inclusive lower bound for a named filter period."""
    now = datetime.utcnow()
    today = datetime(now.year, now.month, now.day)
    if period == "today":
        return today
    if period == "yesterday":
        return today - timedelta(days=1)
    if period == "week":
        return today - timedelta(days=7)
    if period == "month":
        return today - timedelta(days=30)
    return None  # "all"


def _range_end(period: str) -> Optional[datetime]:
    """Upper bound; only 'yesterday' needs one (the start of today)."""
    if period == "yesterday":
        now = datetime.utcnow()
        return datetime(now.year, now.month, now.day)
    return None


@router.post("/sync", response_model=schemas.SyncResponse)
def sync(
    payload: schemas.SyncRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Idempotent upsert of device-side collections, keyed by client UUID."""
    synced_ids: List[str] = []
    for item in payload.collections:
        existing = None
        if item.id:
            existing = db.query(models.Collection).filter(
                models.Collection.id == item.id
            ).first()

        if existing:
            # Already stored — just acknowledge it so the device clears it.
            synced_ids.append(existing.id)
            continue

        record = models.Collection(
            id=item.id,  # keep the client UUID when provided
            user_id=user.id,
            collector_name=user.name,
            verbal_consent=item.verbal_consent,
            child_age=item.child_age,
            child_sex=item.child_sex,
            responder=item.responder,
            responder_other=item.responder_other,
            location_lat=item.location_lat,
            location_lng=item.location_lng,
            location_address=item.location_address,
            collected_at=item.collected_at or datetime.utcnow(),
            synced_at=datetime.utcnow(),
        )
        db.add(record)
        db.flush()  # populate generated id if client didn't send one

        # Persist this collection's questionnaire answers.
        for a in item.answers:
            db.add(models.Answer(
                collection_id=record.id,
                question_id=a.question_id,
                question_code=a.question_code,
                question_title=a.question_title,
                qtype=a.qtype,
                value_bool=a.value_bool,
                value_number=a.value_number,
                value_text=a.value_text,
                photo_filename=a.photo_filename,
            ))

        synced_ids.append(record.id)

    db.commit()
    return schemas.SyncResponse(synced_ids=synced_ids)


@router.post("/photo")
async def upload_photo(
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
):
    """Upload a questionnaire photo (e.g. OPD card). Returns its stored name,
    which the device then references in the answer it syncs."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_IMAGE_EXT:
        ext = ".jpg"
    content = await file.read()
    if len(content) > _MAX_PHOTO_BYTES:
        raise HTTPException(413, "Image too large (max 8 MB).")

    os.makedirs(settings.MEDIA_DIR, exist_ok=True)
    name = f"{uuidlib.uuid4().hex}{ext}"
    with open(os.path.join(settings.MEDIA_DIR, name), "wb") as f:
        f.write(content)
    return {"filename": name}


@router.get("", response_model=List[schemas.CollectionOut])
def list_collections(
    period: str = Query("week", pattern="^(today|yesterday|week|month|all)$"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.Collection).filter(
        models.Collection.user_id == user.id
    )
    start = _range_start(period)
    end = _range_end(period)
    if start is not None:
        q = q.filter(models.Collection.collected_at >= start)
    if end is not None:
        q = q.filter(models.Collection.collected_at < end)
    return q.order_by(models.Collection.collected_at.desc()).all()
