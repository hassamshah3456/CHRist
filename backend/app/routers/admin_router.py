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
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models, payments, schemas
from ..auth import get_current_admin
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/api", tags=["admin"])
ONLINE_WINDOW = timedelta(minutes=3)


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


def _primary_yes_no_codes(db: Session) -> set:
    """Question codes for top-level yes/no screening items (excludes follow-ups)."""
    rows = db.query(models.Question).filter(
        models.Question.qtype == "yes_no"
    ).all()
    return {q.code for q in rows}


def _positivity_counts(db: Session):
    """Mutually exclusive buckets: normal (<3 Yes), triple (3), quadruple (4+)."""
    codes = _primary_yes_no_codes(db)
    q = db.query(models.Answer).filter(models.Answer.value_bool == True)  # noqa: E712
    if codes:
        q = q.filter(models.Answer.question_code.in_(codes))
    else:
        q = q.filter(models.Answer.qtype == "yes_no")
    yes_by_collection = Counter(a.collection_id for a in q.all())
    all_ids = [row[0] for row in db.query(models.Collection.id).all()]
    normal = triple = quadruple = 0
    for cid in all_ids:
        n = yes_by_collection.get(cid, 0)
        if n >= 4:
            quadruple += 1
        elif n >= 3:
            triple += 1
        else:
            normal += 1
    return normal, triple, quadruple


def _count_triple_positive(db: Session) -> int:
    """Submissions with 3+ Yes answers on top-level yes/no screening questions."""
    _, triple, quadruple = _positivity_counts(db)
    return triple + quadruple


def _yes_counts_by_collection(db: Session) -> Counter:
    codes = _primary_yes_no_codes(db)
    q = db.query(models.Answer.collection_id).filter(
        models.Answer.value_bool == True  # noqa: E712
    )
    if codes:
        q = q.filter(models.Answer.question_code.in_(codes))
    else:
        q = q.filter(models.Answer.qtype == "yes_no")
    return Counter(row[0] for row in q.all())


def _apply_collection_search(q, search: Optional[str]):
    if not search or not search.strip():
        return q
    term = f"%{search.strip()}%"
    return q.filter(or_(
        models.Collection.collector_name.ilike(term),
        models.Collection.child_name.ilike(term),
        models.Collection.phone.ilike(term),
        models.Collection.location_address.ilike(term),
        models.User.phone.ilike(term),
        models.User.email.ilike(term),
    ))


def _apply_positive_filter(q, db: Session, positive: str):
    if positive not in ("triple", "quad"):
        return q
    yes_by = _yes_counts_by_collection(db)
    min_yes = 4 if positive == "quad" else 3
    ids = [cid for cid, n in yes_by.items() if n >= min_yes]
    if not ids:
        return q.filter(False)  # noqa: E712
    return q.filter(models.Collection.id.in_(ids))


def _admin_collection_out(c, u, answers) -> schemas.AdminCollectionOut:
    return schemas.AdminCollectionOut(
        id=c.id,
        user_id=c.user_id,
        collector_name=c.collector_name,
        collector_email=u.email,
        collector_phone=u.phone,
        verbal_consent=c.verbal_consent,
        phone=c.phone,
        child_name=c.child_name,
        child_age=c.child_age,
        child_age_months=c.child_age_months,
        child_sex=c.child_sex,
        responder=c.responder,
        responder_other=c.responder_other,
        medical_record=c.medical_record,
        medical_record_photo=c.medical_record_photo,
        card_submitted=c.card_submitted,
        card_approved=c.card_approved,
        vaccines=c.vaccines,
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
            for a in answers
        ],
    )


def _collections_query(
    db: Session,
    period: str,
    collector_id: Optional[str] = None,
    search: Optional[str] = None,
    positive: str = "all",
):
    q = db.query(models.Collection, models.User).join(
        models.User, models.Collection.user_id == models.User.id
    )
    q = _apply_period(q, period)
    if collector_id:
        q = q.filter(models.Collection.user_id == collector_id)
    q = _apply_collection_search(q, search)
    q = _apply_positive_filter(q, db, positive)
    return q


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


def _is_online(user: models.User, now: Optional[datetime] = None) -> bool:
    now = now or datetime.utcnow()
    return bool(user.last_seen and user.last_seen >= now - ONLINE_WINDOW)


def _collector_summaries(
    db: Session,
    users: List[models.User],
    period: str = "all",
) -> List[schemas.CollectorSummary]:
    user_ids = [u.id for u in users if not u.is_admin]
    if not user_ids:
        return []
    q = db.query(models.Collection).filter(
        models.Collection.user_id.in_(user_ids)
    )
    q = _apply_period(q, period)
    cols = q.all()
    by_user_count = Counter(c.user_id for c in cols)
    last_by_user = {}
    for c in cols:
        if c.collected_at and (
            c.user_id not in last_by_user
            or c.collected_at > last_by_user[c.user_id]
        ):
            last_by_user[c.user_id] = c.collected_at
    now = datetime.utcnow()
    rows = [
        schemas.CollectorSummary(
            id=u.id,
            name=u.name,
            phone=u.phone,
            email=u.email,
            upi_address=u.upi_address,
            upi_name=u.upi_name,
            total=by_user_count.get(u.id, 0),
            last_collection=last_by_user.get(u.id),
            signup_lat=u.signup_lat,
            signup_lng=u.signup_lng,
            signup_address=u.signup_address,
            online=_is_online(u, now),
            last_seen=u.last_seen,
            last_lat=u.last_lat,
            last_lng=u.last_lng,
            last_address=u.last_address,
            app_seconds=u.app_seconds or 0,
        )
        for u in users
        if not u.is_admin
    ]
    rows.sort(key=lambda c: (not c.online, -c.total, c.name.lower()))
    return rows


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

    # Age distribution by research-friendly bands (years; <1y uses months).
    age_bands = OrderedDict([
        ("< 1 yr", 0), ("1–4 yrs", 0), ("5–9 yrs", 0),
        ("10–14 yrs", 0), ("15–18 yrs", 0), ("Unknown", 0),
    ])
    ages = []
    for c in cols:
        if c.child_age is None:
            age_bands["Unknown"] += 1
            continue
        ages.append(c.child_age)
        a = c.child_age
        if a < 1:
            age_bands["< 1 yr"] += 1
        elif a <= 4:
            age_bands["1–4 yrs"] += 1
        elif a <= 9:
            age_bands["5–9 yrs"] += 1
        elif a <= 14:
            age_bands["10–14 yrs"] += 1
        else:
            age_bands["15–18 yrs"] += 1
    avg_age = round(sum(ages) / len(ages), 1) if ages else None

    # Per-question Yes/No positivity across all answers (e.g. vaccine coverage).
    yn = defaultdict(lambda: {"yes": 0, "no": 0, "label": ""})
    yn_answers = db.query(models.Answer).filter(
        models.Answer.value_bool.isnot(None)
    ).all()
    for a in yn_answers:
        key = a.question_code or (a.question_id or "")
        yn[key]["label"] = a.question_title or a.question_code or key
        if a.value_bool:
            yn[key]["yes"] += 1
        else:
            yn[key]["no"] += 1
    question_stats = sorted(
        (
            schemas.QuestionStat(
                code=k, label=v["label"], yes=v["yes"], no=v["no"],
                total=v["yes"] + v["no"],
            )
            for k, v in yn.items()
        ),
        key=lambda q: q.total,
        reverse=True,
    )

    collectors = _collector_summaries(db, users)
    positivity_normal, positivity_triple, positivity_quadruple = _positivity_counts(db)
    triple_positive = positivity_triple + positivity_quadruple

    return schemas.AdminStats(
        total=total,
        today=n_today,
        this_week=n_week,
        this_month=n_month,
        triple_positive=triple_positive,
        positivity_normal=positivity_normal,
        positivity_triple=positivity_triple,
        positivity_quadruple=positivity_quadruple,
        consent_yes=consent_yes,
        consent_no=total - consent_yes,
        collectors_count=len(collectors),
        avg_age=avg_age,
        daily=[schemas.DailyPoint(date=k, count=v) for k, v in daily.items()],
        sex_breakdown=[
            schemas.BreakdownItem(label=k, count=v)
            for k, v in sex_counter.items()
        ],
        responder_breakdown=[
            schemas.BreakdownItem(label=k, count=v)
            for k, v in resp_counter.items()
        ],
        age_breakdown=[
            schemas.BreakdownItem(label=k, count=v)
            for k, v in age_bands.items() if v > 0
        ],
        question_stats=question_stats,
        collectors=collectors,
    )


@router.get("/collections", response_model=schemas.AdminCollectionsPage)
def admin_collections(
    period: str = Query("all", pattern="^(today|yesterday|week|month|all)$"),
    collector_id: Optional[str] = None,
    search: Optional[str] = None,
    positive: str = Query("all", pattern="^(all|triple|quad)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    q = _collections_query(db, period, collector_id, search, positive)
    total = q.count()
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    page = min(page, pages)
    rows = (
        q.order_by(models.Collection.collected_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    answers = _answers_by_collection(db, [c.id for c, _ in rows])
    return schemas.AdminCollectionsPage(
        items=[
            _admin_collection_out(c, u, answers.get(c.id, []))
            for c, u in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/collections/map", response_model=List[schemas.CollectionMapPoint])
def admin_collections_map(
    period: str = Query("all", pattern="^(today|yesterday|week|month|all)$"),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Lightweight geo points for the dashboard map (no answers payload)."""
    q = _collections_query(db, period)
    rows = q.order_by(models.Collection.collected_at.desc()).all()
    return [
        schemas.CollectionMapPoint(
            id=c.id,
            child_name=c.child_name,
            collector_name=c.collector_name,
            child_age=c.child_age,
            child_age_months=c.child_age_months,
            verbal_consent=c.verbal_consent,
            location_lat=c.location_lat,
            location_lng=c.location_lng,
            collected_at=c.collected_at,
        )
        for c, _ in rows
        if c.location_lat is not None and c.location_lng is not None
    ]


@router.delete("/collections/{collection_id}", status_code=204)
def delete_collection(
    collection_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Permanently delete a submission, its answers, and any uploaded photos."""
    c = db.query(models.Collection).filter(
        models.Collection.id == collection_id
    ).first()
    if c is None:
        raise HTTPException(404, "Collection not found.")

    # Gather photo filenames before the row (and cascaded answers) are removed.
    photo_names = []
    if c.medical_record_photo:
        photo_names.append(c.medical_record_photo)
    for a in c.answers:
        if a.photo_filename:
            photo_names.append(a.photo_filename)

    db.delete(c)  # answers are removed via cascade="all, delete-orphan"
    db.commit()

    for name in photo_names:
        if not name or "/" in name or "\\" in name or ".." in name:
            continue
        path = os.path.join(settings.MEDIA_DIR, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass


@router.get("/collectors", response_model=List[schemas.CollectorSummary])
def admin_collectors(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    users = db.query(models.User).filter(models.User.is_admin == False).all()  # noqa: E712
    return _collector_summaries(db, users)


# ---------- Collector groups ----------
def _group_or_404(db: Session, group_id: str) -> models.CollectorGroup:
    group = db.query(models.CollectorGroup).filter(
        models.CollectorGroup.id == group_id
    ).first()
    if group is None:
        raise HTTPException(404, "Collector group not found.")
    return group


def _validated_members(db: Session, member_ids: List[str]) -> List[models.User]:
    ids = list(dict.fromkeys(member_ids))
    members = db.query(models.User).filter(models.User.id.in_(ids)).all() if ids else []
    found = {u.id for u in members if not u.is_admin}
    if len(found) != len(ids):
        raise HTTPException(400, "One or more selected collectors are invalid.")
    return [u for u in members if not u.is_admin]


@router.get("/groups", response_model=List[schemas.CollectorGroupSummary])
def list_groups(
    period: str = Query("all", pattern="^(today|yesterday|week|month|all)$"),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    groups = db.query(models.CollectorGroup).order_by(
        models.CollectorGroup.created_at.desc()
    ).all()
    result = []
    for group in groups:
        members = _collector_summaries(db, list(group.members), period)
        result.append(schemas.CollectorGroupSummary(
            id=group.id,
            name=group.name,
            members_count=len(members),
            collections_count=sum(m.total for m in members),
            online_count=sum(1 for m in members if m.online),
            created_at=group.created_at,
        ))
    return result


@router.post("/groups", response_model=schemas.CollectorGroupDetail, status_code=201)
def create_group(
    body: schemas.CollectorGroupIn,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    if not body.name.strip():
        raise HTTPException(400, "Group name is required.")
    group = models.CollectorGroup(
        name=body.name.strip(),
        members=_validated_members(db, body.member_ids),
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group_detail(group.id, "all", db, admin)


@router.put("/groups/{group_id}", response_model=schemas.CollectorGroupDetail)
def update_group(
    group_id: str,
    body: schemas.CollectorGroupIn,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    group = _group_or_404(db, group_id)
    if not body.name.strip():
        raise HTTPException(400, "Group name is required.")
    group.name = body.name.strip()
    group.members = _validated_members(db, body.member_ids)
    db.commit()
    return group_detail(group.id, "all", db, admin)


@router.get("/groups/{group_id}", response_model=schemas.CollectorGroupDetail)
def group_detail(
    group_id: str,
    period: str = Query("all", pattern="^(today|yesterday|week|month|all)$"),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    group = _group_or_404(db, group_id)
    members = _collector_summaries(db, list(group.members), period)
    payment_rows, total_due, total_paid, cfg = _collector_payments(
        db, list(group.members)
    )
    return schemas.CollectorGroupDetail(
        id=group.id,
        name=group.name,
        members_count=len(members),
        collections_count=sum(m.total for m in members),
        online_count=sum(1 for m in members if m.online),
        created_at=group.created_at,
        members=members,
        total_due=total_due,
        total_paid=total_paid,
        currency=cfg["currency"],
        payments=payment_rows,
    )


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(
    group_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    group = _group_or_404(db, group_id)
    db.delete(group)
    db.commit()


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
        "id", "collected_at", "collector_name", "collector_phone", "collector_email",
        "phone", "verbal_consent", "child_name", "child_age", "child_age_months", "child_sex", "responder",
        "responder_other", "medical_record", "medical_record_photo",
        "card_submitted", "card_approved", "vaccines",
        "location_lat", "location_lng", "location_address",
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
            u.phone or "",
            u.email or "",
            c.phone or "",
            "yes" if c.verbal_consent else "no",
            c.child_name or "",
            c.child_age if c.child_age is not None else "",
            c.child_age_months if c.child_age_months is not None else "",
            c.child_sex or "",
            c.responder or "",
            c.responder_other or "",
            "yes" if c.medical_record else ("no" if c.medical_record is not None else ""),
            c.medical_record_photo or "",
            "yes" if c.card_submitted else "no",
            "yes" if c.card_approved else "no",
            c.vaccines or "",
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


# ---------- Instructions ----------
# Per-language keys; "en" keeps the original key for backward compatibility.
_INSTRUCTIONS_KEYS = {
    "en": "instructions_html",
    "hi": "instructions_html_hi",
    "kn": "instructions_html_kn",
}


@router.get("/instructions", response_model=schemas.InstructionsMulti)
def get_instructions(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    return schemas.InstructionsMulti(
        en=payments.get_setting(db, _INSTRUCTIONS_KEYS["en"]),
        hi=payments.get_setting(db, _INSTRUCTIONS_KEYS["hi"]),
        kn=payments.get_setting(db, _INSTRUCTIONS_KEYS["kn"]),
    )


@router.put("/instructions", response_model=schemas.InstructionsMulti)
def update_instructions(
    body: schemas.InstructionsMulti,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    payments.set_settings(db, {
        _INSTRUCTIONS_KEYS["en"]: body.en or "",
        _INSTRUCTIONS_KEYS["hi"]: body.hi or "",
        _INSTRUCTIONS_KEYS["kn"]: body.kn or "",
    })
    return body


# ---------- Payments ----------
def _payment_config_schema(cfg: dict) -> schemas.PaymentConfig:
    return schemas.PaymentConfig(
        per_entry=cfg["per_entry"],
        card_entry=cfg["card_entry"],
        training=cfg["training"],
        currency=cfg["currency"],
    )


def _collector_payments(db: Session, users: List[models.User]):
    """Payout rows and totals for a list of collectors."""
    cfg = payments.get_config(db)
    rows = []
    user_ids = []
    for u in users:
        if u.is_admin:
            continue
        user_ids.append(u.id)
        due = payments.collector_due(db, u, cfg)
        last = payments.last_payout(db, u.id)
        rows.append(schemas.CollectorPayment(
            id=u.id, name=u.name, phone=u.phone, email=u.email,
            upi_address=u.upi_address, upi_name=u.upi_name,
            total_entries=due["total_entries"],
            unpaid_entries=due["unpaid_entries"],
            regular_unpaid_entries=due["regular_unpaid_entries"],
            card_entries=due["card_entries"],
            approved_card_entries=due["approved_card_entries"],
            approved_card_unpaid_entries=due["approved_card_unpaid_entries"],
            pending_card_entries=due["pending_card_entries"],
            per_entry=cfg["per_entry"], card_entry=cfg["card_entry"],
            training=cfg["training"],
            training_paid=due["training_paid"], due=due["due"],
            currency=cfg["currency"], last_payout=last,
        ))
    rows.sort(key=lambda r: r.due, reverse=True)
    total_due = round(sum(r.due for r in rows), 2)
    total_paid = 0.0
    if user_ids:
        total_paid = round(
            float(
                db.query(func.coalesce(func.sum(models.Payout.amount), 0))
                .filter(models.Payout.user_id.in_(user_ids))
                .scalar()
                or 0
            ),
            2,
        )
    return rows, total_due, total_paid, cfg


@router.get("/payments", response_model=schemas.PaymentsOverview)
def payments_overview(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Per-collector payout status plus the current rates."""
    users = [u for u in db.query(models.User).all() if not u.is_admin]
    rows, total_due, total_paid, cfg = _collector_payments(db, users)
    return schemas.PaymentsOverview(
        config=_payment_config_schema(cfg),
        collectors=rows,
        total_due=total_due,
        total_paid=total_paid,
    )


@router.put("/payment-config", response_model=schemas.PaymentConfig)
def update_payment_config(
    body: schemas.PaymentConfig,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    payments.set_config(db, body.per_entry, body.training, body.card_entry)
    return _payment_config_schema(payments.get_config(db))


@router.get("/card-approvals", response_model=List[schemas.AdminCollectionOut])
def card_approvals(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Card/photo entries waiting for admin approval before card-rate payout."""
    rows = (
        db.query(models.Collection, models.User)
        .join(models.User, models.Collection.user_id == models.User.id)
        .filter(
            models.Collection.paid == False,  # noqa: E712
            models.Collection.card_submitted == True,  # noqa: E712
            models.Collection.card_approved == False,  # noqa: E712
        )
        .order_by(models.Collection.collected_at.desc())
        .all()
    )
    return [
        schemas.AdminCollectionOut(
            id=c.id,
            user_id=c.user_id,
            collector_name=c.collector_name,
            collector_email=u.email,
            collector_phone=u.phone,
            verbal_consent=c.verbal_consent,
            phone=c.phone,
            child_name=c.child_name,
            child_age=c.child_age,
            child_age_months=c.child_age_months,
            child_sex=c.child_sex,
            responder=c.responder,
            responder_other=c.responder_other,
            medical_record=c.medical_record,
            medical_record_photo=c.medical_record_photo,
            card_submitted=c.card_submitted,
            card_approved=c.card_approved,
            vaccines=c.vaccines,
            location_lat=c.location_lat,
            location_lng=c.location_lng,
            location_address=c.location_address,
            collected_at=c.collected_at,
            answers=[],
        )
        for c, u in rows
    ]


@router.post("/collections/{collection_id}/approve-card", response_model=schemas.AdminCollectionOut)
def approve_card_entry(
    collection_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    row = (
        db.query(models.Collection, models.User)
        .join(models.User, models.Collection.user_id == models.User.id)
        .filter(models.Collection.id == collection_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, "Collection not found.")
    c, u = row
    if not c.card_submitted:
        raise HTTPException(400, "This entry has no submitted card.")
    if c.paid:
        raise HTTPException(400, "This entry has already been settled.")
    c.card_approved = True
    db.commit()
    db.refresh(c)
    return schemas.AdminCollectionOut(
        id=c.id,
        user_id=c.user_id,
        collector_name=c.collector_name,
        collector_email=u.email,
        collector_phone=u.phone,
        verbal_consent=c.verbal_consent,
        phone=c.phone,
        child_name=c.child_name,
        child_age=c.child_age,
        child_age_months=c.child_age_months,
        child_sex=c.child_sex,
        responder=c.responder,
        responder_other=c.responder_other,
        medical_record=c.medical_record,
        medical_record_photo=c.medical_record_photo,
        card_submitted=c.card_submitted,
        card_approved=c.card_approved,
        vaccines=c.vaccines,
        location_lat=c.location_lat,
        location_lng=c.location_lng,
        location_address=c.location_address,
        collected_at=c.collected_at,
        answers=[],
    )


@router.post("/collectors/{user_id}/pay", response_model=schemas.PayoutOut)
def mark_collector_paid(
    user_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Settle a collector: mark their unpaid entries paid, record the payout,
    and reset their due counter to zero."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or user.is_admin:
        raise HTTPException(404, "Collector not found.")
    cfg = payments.get_config(db)
    payout = payments.mark_paid(db, user, cfg)
    return payout
