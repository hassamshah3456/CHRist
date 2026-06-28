"""Collection sync + listing endpoints (all require auth)."""
import logging
import os
import uuid as uuidlib
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from .. import models, payments, schemas
from ..auth import get_current_user
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/collections", tags=["collections"])
logger = logging.getLogger(__name__)

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
    """Idempotent upsert of device-side collections, keyed by client UUID.

    Each record is committed independently so a single problematic entry can
    never block the rest of a collector's queue from syncing. Only the ids the
    server actually persisted are returned, so the device keeps retrying the
    failed ones without losing the successful ones.
    """
    synced_ids: List[str] = []
    for item in payload.collections:
        try:
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
                phone=item.phone,
                child_name=item.child_name,
                child_age=item.child_age,
                child_age_months=item.child_age_months,
                child_sex=item.child_sex,
                responder=item.responder,
                responder_other=item.responder_other,
                medical_record=item.medical_record,
                medical_record_photo=item.medical_record_photo,
                card_submitted=bool(item.card_submitted or item.medical_record_photo),
                card_approved=False,
                vaccines=item.vaccines,
                location_lat=item.location_lat,
                location_lng=item.location_lng,
                location_address=item.location_address,
                collected_at=item.collected_at or datetime.utcnow(),
                synced_at=datetime.utcnow(),
            )
            db.add(record)
            db.flush()  # populate generated id if client didn't send one

            # Persist this collection's questionnaire answers. Snapshot fields
            # are truncated to their column widths so an unusually long title
            # or code can't fail the insert.
            for a in item.answers:
                db.add(models.Answer(
                    collection_id=record.id,
                    question_id=a.question_id[:64] if a.question_id else None,
                    question_code=(a.question_code or "")[:64],
                    question_title=a.question_title[:512] if a.question_title else None,
                    qtype=a.qtype,
                    value_bool=a.value_bool,
                    value_number=a.value_number,
                    value_text=a.value_text,
                    photo_filename=a.photo_filename,
                ))

            db.commit()
            synced_ids.append(record.id)
        except Exception as exc:
            # Isolate the failure: roll back just this record and keep going so
            # the collector's other pending entries still sync. The error reason
            # is included inline so it's visible even when grepping the message.
            db.rollback()
            logger.exception(
                "Failed to sync collection %s for user %s: %r",
                item.id, user.id, exc,
            )
            continue

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


@router.get("/instructions", response_model=schemas.Instructions)
def collector_instructions(
    lang: str = Query("en"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """The admin-authored instructions in the requested language (English
    fallback if that language is empty)."""
    keys = {"en": "instructions_html", "hi": "instructions_html_hi",
            "kn": "instructions_html_kn"}
    html = payments.get_setting(db, keys.get(lang, keys["en"]))
    if not html:
        html = payments.get_setting(db, keys["en"])
    return schemas.Instructions(html=html)


@router.get("/payment", response_model=schemas.MyPayment)
def my_payment(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Payment summary for the signed-in collector (app payment screen)."""
    cfg = payments.get_config(db)
    due = payments.collector_due(db, user, cfg)
    last = payments.last_payout(db, user.id)
    return schemas.MyPayment(
        currency=cfg["currency"],
        per_entry=cfg["per_entry"],
        card_entry=cfg["card_entry"],
        training=cfg["training"],
        total_entries=due["total_entries"],
        unpaid_entries=due["unpaid_entries"],
        regular_unpaid_entries=due["regular_unpaid_entries"],
        card_entries=due["card_entries"],
        approved_card_entries=due["approved_card_entries"],
        approved_card_unpaid_entries=due["approved_card_unpaid_entries"],
        pending_card_entries=due["pending_card_entries"],
        due=due["due"],
        training_paid=due["training_paid"],
        last_payout=last,
    )


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
