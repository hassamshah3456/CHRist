"""Dashboard statistics endpoint."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=schemas.StatsResponse)
def stats(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    base = db.query(models.Collection).filter(
        models.Collection.user_id == user.id
    )

    now = datetime.utcnow()
    today = datetime(now.year, now.month, now.day)
    week = today - timedelta(days=7)
    month = today - timedelta(days=30)

    def count_since(since):
        return base.filter(models.Collection.collected_at >= since).count()

    consent_yes = base.filter(models.Collection.verbal_consent.is_(True)).count()
    total = base.count()

    return schemas.StatsResponse(
        total=total,
        today=count_since(today),
        this_week=count_since(week),
        this_month=count_since(month),
        consent_yes=consent_yes,
        consent_no=total - consent_yes,
    )
