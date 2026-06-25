"""Admin/management endpoints powering the web dashboard.

All routes require an admin account and return data across ALL collectors.
Prefixed with /api so they don't collide with the /admin static mount.
"""
import csv
import io
from collections import Counter, OrderedDict
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_admin
from ..database import get_db

router = APIRouter(prefix="/api", tags=["admin"])


def _today() -> datetime:
    n = datetime.utcnow()
    return datetime(n.year, n.month, n.day)


def _apply_period(query, period: str):
    """Filter a Collection query by a named period."""
    today = _today()
    if period == "today":
        return query.filter(models.Collection.collected_at >= today)
    if period == "yesterday":
        return query.filter(
            models.Collection.collected_at >= today - timedelta(days=1),
            models.Collection.collected_at < today,
        )
    if period == "week":
        return query.filter(
            models.Collection.collected_at >= today - timedelta(days=7)
        )
    if period == "month":
        return query.filter(
            models.Collection.collected_at >= today - timedelta(days=30)
        )
    return query  # "all"


@router.get("/stats", response_model=schemas.AdminStats)
def admin_stats(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    cols = db.query(models.Collection).all()
    users = db.query(models.User).all()

    today = _today()
    week = today - timedelta(days=7)
    month = today - timedelta(days=30)

    total = len(cols)
    n_today = sum(1 for c in cols if c.collected_at and c.collected_at >= today)
    n_week = sum(1 for c in cols if c.collected_at and c.collected_at >= week)
    n_month = sum(1 for c in cols if c.collected_at and c.collected_at >= month)
    consent_yes = sum(1 for c in cols if c.verbal_consent)

    # Daily series for the last 30 days (zero-filled).
    daily = OrderedDict()
    for i in range(29, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        daily[d] = 0
    for c in cols:
        if c.collected_at and c.collected_at >= month:
            key = c.collected_at.strftime("%Y-%m-%d")
            if key in daily:
                daily[key] += 1

    sex_counter = Counter((c.child_sex or "unknown") for c in cols)
    resp_counter = Counter((c.responder or "unknown") for c in cols)

    # Per-collector rollup.
    by_user_count = Counter(c.user_id for c in cols)
    last_by_user = {}
    for c in cols:
        if c.collected_at and (
            c.user_id not in last_by_user
            or c.collected_at > last_by_user[c.user_id]
        ):
            last_by_user[c.user_id] = c.collected_at

    collectors = [
        schemas.CollectorSummary(
            id=u.id,
            name=u.name,
            email=u.email,
            upi_address=u.upi_address,
            upi_name=u.upi_name,
            total=by_user_count.get(u.id, 0),
            last_collection=last_by_user.get(u.id),
            signup_lat=u.signup_lat,
            signup_lng=u.signup_lng,
            signup_address=u.signup_address,
        )
        for u in users
        if not u.is_admin  # don't list admin accounts as collectors
    ]
    collectors.sort(key=lambda c: c.total, reverse=True)

    return schemas.AdminStats(
        total=total,
        today=n_today,
        this_week=n_week,
        this_month=n_month,
        consent_yes=consent_yes,
        consent_no=total - consent_yes,
        collectors_count=len(collectors),
        daily=[schemas.DailyPoint(date=k, count=v) for k, v in daily.items()],
        sex_breakdown=[
            schemas.BreakdownItem(label=k, count=v)
            for k, v in sex_counter.items()
        ],
        responder_breakdown=[
            schemas.BreakdownItem(label=k, count=v)
            for k, v in resp_counter.items()
        ],
        collectors=collectors,
    )


@router.get("/collections", response_model=List[schemas.AdminCollectionOut])
def admin_collections(
    period: str = Query("all", pattern="^(today|yesterday|week|month|all)$"),
    collector_id: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    q = db.query(models.Collection, models.User).join(
        models.User, models.Collection.user_id == models.User.id
    )
    q = _apply_period(q, period)
    if collector_id:
        q = q.filter(models.Collection.user_id == collector_id)
    rows = q.order_by(models.Collection.collected_at.desc()).all()

    return [
        schemas.AdminCollectionOut(
            id=c.id,
            user_id=c.user_id,
            collector_name=c.collector_name,
            collector_email=u.email,
            verbal_consent=c.verbal_consent,
            child_age=c.child_age,
            child_sex=c.child_sex,
            responder=c.responder,
            responder_other=c.responder_other,
            location_lat=c.location_lat,
            location_lng=c.location_lng,
            location_address=c.location_address,
            collected_at=c.collected_at,
        )
        for c, u in rows
    ]


@router.get("/collectors", response_model=List[schemas.CollectorSummary])
def admin_collectors(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    # Reuse the rollup from admin_stats for consistency.
    return admin_stats(db=db, admin=admin).collectors


@router.get("/export.csv")
def export_csv(
    period: str = Query("all", pattern="^(today|yesterday|week|month|all)$"),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Download all (filtered) collections as a CSV (opens in Excel)."""
    q = db.query(models.Collection, models.User).join(
        models.User, models.Collection.user_id == models.User.id
    )
    q = _apply_period(q, period)
    rows = q.order_by(models.Collection.collected_at.desc()).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "collected_at", "collector_name", "collector_email",
        "verbal_consent", "child_age", "child_sex", "responder",
        "responder_other", "location_lat", "location_lng", "location_address",
    ])
    for c, u in rows:
        writer.writerow([
            c.id,
            c.collected_at.isoformat() if c.collected_at else "",
            c.collector_name,
            u.email,
            "yes" if c.verbal_consent else "no",
            c.child_age if c.child_age is not None else "",
            c.child_sex or "",
            c.responder or "",
            c.responder_other or "",
            c.location_lat if c.location_lat is not None else "",
            c.location_lng if c.location_lng is not None else "",
            c.location_address or "",
        ])
    buf.seek(0)
    filename = f"collections_{period}_{datetime.utcnow():%Y%m%d}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
