"""Questionnaire management (admin) and delivery (collector)."""
import json
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_admin, get_current_user
from ..database import get_db

# Admin CRUD lives under /api/questions; collectors fetch the active set at
# /questionnaire.
router = APIRouter(prefix="/api/questions", tags=["questions"])
public_router = APIRouter(tags=["questionnaire"])


def _to_out(q: models.Question) -> schemas.QuestionOut:
    options = []
    if q.options_json:
        try:
            options = json.loads(q.options_json)
        except Exception:
            options = []
    return schemas.QuestionOut(
        id=q.id,
        code=q.code,
        order_index=q.order_index,
        title=q.title,
        help_text=q.help_text,
        qtype=q.qtype,
        options=options,
        required=q.required,
        secondary_aim=q.secondary_aim,
        photo_on_yes=q.photo_on_yes,
        note_on_yes=q.note_on_yes,
        is_active=q.is_active,
    )


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (slug or "question")[:48]


def _unique_code(db: Session, base: str, exclude_id: str = "") -> str:
    code = base
    i = 1
    while True:
        existing = db.query(models.Question).filter(
            models.Question.code == code
        ).first()
        if not existing or existing.id == exclude_id:
            return code
        i += 1
        code = f"{base}_{i}"


# ---------- Admin CRUD ----------
@router.get("", response_model=List[schemas.QuestionOut])
def list_questions(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    qs = db.query(models.Question).order_by(models.Question.order_index).all()
    return [_to_out(q) for q in qs]


@router.post("", response_model=schemas.QuestionOut)
def create_question(
    payload: schemas.QuestionIn,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    if payload.qtype not in schemas.QTYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid question type.")

    code = _unique_code(db, payload.code or _slugify(payload.title))
    order = payload.order_index
    if order is None:
        order = (db.query(func.max(models.Question.order_index)).scalar() or 0) + 1

    q = models.Question(
        code=code,
        order_index=order,
        title=payload.title,
        help_text=payload.help_text,
        qtype=payload.qtype,
        options_json=json.dumps(payload.options) if payload.options else None,
        required=payload.required,
        secondary_aim=payload.secondary_aim,
        photo_on_yes=payload.photo_on_yes,
        note_on_yes=payload.note_on_yes,
        is_active=payload.is_active,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _to_out(q)


@router.put("/{qid}", response_model=schemas.QuestionOut)
def update_question(
    qid: str,
    payload: schemas.QuestionIn,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    q = db.query(models.Question).filter(models.Question.id == qid).first()
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")
    if payload.qtype not in schemas.QTYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid question type.")

    if payload.code and payload.code != q.code:
        q.code = _unique_code(db, payload.code, exclude_id=q.id)
    q.title = payload.title
    q.help_text = payload.help_text
    q.qtype = payload.qtype
    q.options_json = json.dumps(payload.options) if payload.options else None
    q.required = payload.required
    q.secondary_aim = payload.secondary_aim
    q.photo_on_yes = payload.photo_on_yes
    q.note_on_yes = payload.note_on_yes
    q.is_active = payload.is_active
    if payload.order_index is not None:
        q.order_index = payload.order_index
    db.commit()
    db.refresh(q)
    return _to_out(q)


@router.delete("/{qid}")
def delete_question(
    qid: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    q = db.query(models.Question).filter(models.Question.id == qid).first()
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")
    db.delete(q)
    db.commit()
    return {"ok": True}


@router.post("/reorder")
def reorder_questions(
    payload: schemas.ReorderRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    for idx, qid in enumerate(payload.ordered_ids):
        q = db.query(models.Question).filter(models.Question.id == qid).first()
        if q:
            q.order_index = idx
    db.commit()
    return {"ok": True}


# ---------- Collector delivery ----------
@public_router.get("/questionnaire", response_model=List[schemas.QuestionOut])
def get_questionnaire(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    qs = (
        db.query(models.Question)
        .filter(models.Question.is_active.is_(True))
        .order_by(models.Question.order_index)
        .all()
    )
    return [_to_out(q) for q in qs]
