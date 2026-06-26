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
CARD_ENTRY_KEY = "payment_card_entry"
TRAINING_KEY = "payment_training"
CURRENCY = "₹"


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(models.Setting).filter(models.Setting.key == key).first()
    return row.value if row and row.value is not None else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(models.Setting).filter(models.Setting.key == key).first()
    if row is None:
        db.add(models.Setting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def set_settings(db: Session, pairs: dict) -> None:
    """Update several settings in one transaction (e.g. instructions HTML)."""
    for key, value in pairs.items():
        row = db.query(models.Setting).filter(models.Setting.key == key).first()
        if row is None:
            db.add(models.Setting(key=key, value=value))
        else:
            row.value = value
    db.commit()


def get_config(db: Session) -> dict:
    rows = {s.key: s.value for s in db.query(models.Setting).all()}

    def _num(key: str) -> float:
        try:
            return float(rows.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    return {
        "per_entry": _num(PER_ENTRY_KEY),
        "card_entry": _num(CARD_ENTRY_KEY),
        "training": _num(TRAINING_KEY),
        "currency": CURRENCY,
    }


def set_config(db: Session, per_entry: float, training: float, card_entry: float = 0) -> None:
    for key, val in (
        (PER_ENTRY_KEY, per_entry),
        (CARD_ENTRY_KEY, card_entry),
        (TRAINING_KEY, training),
    ):
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
    regular_unpaid = db.query(models.Collection).filter(
        models.Collection.user_id == user.id,
        models.Collection.paid == False,  # noqa: E712
        models.Collection.card_submitted == False,  # noqa: E712
    ).count()
    approved_card_unpaid = db.query(models.Collection).filter(
        models.Collection.user_id == user.id,
        models.Collection.paid == False,  # noqa: E712
        models.Collection.card_submitted == True,  # noqa: E712
        models.Collection.card_approved == True,  # noqa: E712
    ).count()
    pending_card = db.query(models.Collection).filter(
        models.Collection.user_id == user.id,
        models.Collection.paid == False,  # noqa: E712
        models.Collection.card_submitted == True,  # noqa: E712
        models.Collection.card_approved == False,  # noqa: E712
    ).count()
    approved_card_total = db.query(models.Collection).filter(
        models.Collection.user_id == user.id,
        models.Collection.card_submitted == True,  # noqa: E712
        models.Collection.card_approved == True,  # noqa: E712
    ).count()
    card_total = db.query(models.Collection).filter(
        models.Collection.user_id == user.id,
        models.Collection.card_submitted == True,  # noqa: E712
    ).count()

    unpaid = regular_unpaid + approved_card_unpaid
    due = regular_unpaid * cfg["per_entry"] + approved_card_unpaid * cfg["card_entry"]
    if not user.training_paid:
        due += cfg["training"]
    return {
        "total_entries": total,
        "unpaid_entries": unpaid,
        "regular_unpaid_entries": regular_unpaid,
        "card_entries": card_total,
        "approved_card_entries": approved_card_total,
        "approved_card_unpaid_entries": approved_card_unpaid,
        "pending_card_entries": pending_card,
        "due": round(due, 2),
        "training_paid": user.training_paid,
    }


def mark_paid(db: Session, user: models.User, cfg: dict) -> models.Payout:
    """Settle a collector: flag unpaid entries paid, pay training, record it."""
    unpaid = db.query(models.Collection).filter(
        models.Collection.user_id == user.id,
        models.Collection.paid == False,  # noqa: E712
        (
            (models.Collection.card_submitted == False)  # noqa: E712
            | (models.Collection.card_approved == True)  # noqa: E712
        ),
    ).all()
    regular_count = sum(1 for c in unpaid if not c.card_submitted)
    card_count = sum(1 for c in unpaid if c.card_submitted and c.card_approved)
    for c in unpaid:
        c.paid = True

    training_included = not user.training_paid
    amount = (
        regular_count * cfg["per_entry"]
        + card_count * cfg["card_entry"]
        + (cfg["training"] if training_included else 0)
    )
    user.training_paid = True

    payout = models.Payout(
        user_id=user.id,
        amount=round(amount, 2),
        entries_count=regular_count,
        per_entry=cfg["per_entry"],
        card_entries_count=card_count,
        card_per_entry=cfg["card_entry"],
        training_included=training_included,
    )
    db.add(payout)
    db.commit()
    db.refresh(payout)
    return payout
