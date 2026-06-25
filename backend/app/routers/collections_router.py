"""Collection sync + listing endpoints (all require auth)."""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/collections", tags=["collections"])


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
        synced_ids.append(record.id)

    db.commit()
    return schemas.SyncResponse(synced_ids=synced_ids)


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
