"""Admin/management endpoints powering the web dashboard.

All routes require an admin account and return data across ALL collectors.
Prefixed with /api so they don't collide with the /admin static mount.
"""
import csv
import io
import os
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_admin
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/api", tags=["admin"])


def _answers_by_collection(db: Session, collection_ids: List[str]):
    """Fetch answers for many collections in one query, grouped by collection."""
    grouped = defaultdict(list)
    if not collection_ids:
        return grouped
    rows = db.query(models.Answer).filter(
        models.Answer.collection_id.in_(collection_ids)
    ).all()
    for a in rows:
        grouped[a.collection_id].append(a)
    return grouped


def _answer_display(a: models.Answer) -> str:
    """Human-readable answer value for CSV/quick views."""
    if a.value_bool is not None:
        base = "yes" if a.value_bool else "no"
    elif a.value_number is not None:
        base = str(a.value_number)
    else:
        base = a.value_text or ""
    if a.photo_filename:
        base = (base + " [photo]").strip()
    return base


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
    answers = _answers_by_collection(db, [c.id for c, _ in rows])

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
            answers=[
                schemas.AnswerOut(
                    question_code=a.question_code,
                    question_title=a.question_title,
                    qtype=a.qtype,
                    value_bool=a.value_bool,
                    value_number=a.value_number,
                    value_text=a.value_text,
                    photo_filename=a.photo_filename,
                )
                for a in answers.get(c.id, [])
            ],
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

    # Build dynamic answer columns (one per question code present), ordered by
    # the questionnaire's display order.
    grouped = _answers_by_collection(db, [c.id for c, _ in rows])
    code_title = {}
    for alist in grouped.values():
        for a in alist:
            code_title.setdefault(a.question_code, a.question_title or a.question_code)
    order_map = {
        qq.code: qq.order_index
        for qq in db.query(models.Question).all()
    }
    answer_codes = sorted(code_title.keys(), key=lambda c: order_map.get(c, 9999))

    base_cols = [
        "id", "collected_at", "collector_name", "collector_email",
        "verbal_consent", "child_age", "child_sex", "responder",
        "responder_other", "location_lat", "location_lng", "location_address",
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(base_cols + [f"Q:{code_title[c]}" for c in answer_codes])
    for c, u in rows:
        by_code = {a.question_code: a for a in grouped.get(c.id, [])}
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
        ] + [
            _answer_display(by_code[code]) if code in by_code else ""
            for code in answer_codes
        ])
    buf.seek(0)
    filename = f"collections_{period}_{datetime.utcnow():%Y%m%d}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/photos/{filename}")
def get_photo(
    filename: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Serve an uploaded photo to admins only (these are medical records)."""
    # Guard against path traversal — only a bare filename is allowed.
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename.")
    path = os.path.join(settings.MEDIA_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(404, "Photo not found.")
    return FileResponse(path)
