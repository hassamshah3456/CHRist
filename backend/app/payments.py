"""Shared payout helpers used by the collector and admin routers.

Payment rates live in the `settings` table (admin-configurable). A collector's
"due" amount is their count of unpaid entries × per-entry rate, plus the
one-time training fee if it hasn't been paid yet. Marking a collector paid flips
their unpaid entries to paid and records a Payout, so the due counter resets.
"""
from typing import Optional

from sqlalchemy.orm import Session

from . import models

PER_ENTRY_KEY = "payment_per_entry"
TRAINING_KEY = "payment_training"
CURRENCY = "₹"


def get_config(db: Session) -> dict:
    rows = {s.key: s.value for s in db.query(models.Setting).all()}

    def _num(key: str) -> float:
        try:
            return float(rows.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    return {
        "per_entry": _num(PER_ENTRY_KEY),
        "training": _num(TRAINING_KEY),
        "currency": CURRENCY,
    }


def set_config(db: Session, per_entry: float, training: float) -> None:
    for key, val in ((PER_ENTRY_KEY, per_entry), (TRAINING_KEY, training)):
        row = db.query(models.Setting).filter(models.Setting.key == key).first()
        if row is None:
            db.add(models.Setting(key=key, value=str(val)))
        else:
            row.value = str(val)
    db.commit()


def last_payout(db: Session, user_id: str) -> Optional[models.Payout]:
    return (
        db.query(models.Payout)
        .filter(models.Payout.user_id == user_id)
        .order_by(models.Payout.created_at.desc())
        .first()
    )


def collector_due(db: Session, user: models.User, cfg: dict) -> dict:
    """Compute payout figures for one collector."""
    total = db.query(models.Collection).filter(
        models.Collection.user_id == user.id
    ).count()
    unpaid = db.query(models.Collection).filter(
        models.Collection.user_id == user.id,
        models.Collection.paid == False,  # noqa: E712
    ).count()
    due = unpaid * cfg["per_entry"]
    if not user.training_paid:
        due += cfg["training"]
    return {
        "total_entries": total,
        "unpaid_entries": unpaid,
        "due": round(due, 2),
        "training_paid": user.training_paid,
    }


def mark_paid(db: Session, user: models.User, cfg: dict) -> models.Payout:
    """Settle a collector: flag unpaid entries paid, pay training, record it."""
    unpaid = db.query(models.Collection).filter(
        models.Collection.user_id == user.id,
        models.Collection.paid == False,  # noqa: E712
    ).all()
    count = len(unpaid)
    for c in unpaid:
        c.paid = True

    training_included = not user.training_paid
    amount = count * cfg["per_entry"] + (cfg["training"] if training_included else 0)
    user.training_paid = True

    payout = models.Payout(
        user_id=user.id,
        amount=round(amount, 2),
        entries_count=count,
        per_entry=cfg["per_entry"],
        training_included=training_included,
    )
    db.add(payout)
    db.commit()
    db.refresh(payout)
    return payout
