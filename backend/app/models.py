"""Database models."""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


# Many-to-many: a collector can belong to several groups.
group_members = Table(
    "group_members",
    Base.metadata,
    Column("group_id", String(36), ForeignKey("collector_groups.id"),
           primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id"), primary_key=True),
)


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    # String lengths are explicit so the schema is valid on MySQL (VARCHAR
    # needs a length, especially for primary keys and indexed/unique columns).
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    # Role: admins can view all collectors' data via the web dashboard.
    is_admin = Column(Boolean, nullable=False, default=False)

    # Payment details
    upi_address = Column(String(255), nullable=False)  # e.g. name@bank
    upi_name = Column(String(255), nullable=True)      # account holder if different

    # Where the collector signed up (captured at registration)
    signup_lat = Column(Float, nullable=True)
    signup_lng = Column(Float, nullable=True)
    signup_address = Column(String(512), nullable=True)

    # Whether the one-time training fee has been paid out to this collector.
    training_paid = Column(Boolean, nullable=False, default=False)

    # Presence: updated by the app's heartbeat so admins can see who is online
    # right now and where.
    last_seen = Column(DateTime, nullable=True)
    last_lat = Column(Float, nullable=True)
    last_lng = Column(Float, nullable=True)
    last_address = Column(String(512), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    collections = relationship("Collection", back_populates="user")
    groups = relationship(
        "CollectorGroup", secondary=group_members, back_populates="members"
    )


class Collection(Base):
    __tablename__ = "collections"

    # Client-generated UUID so offline records keep a stable identity and
    # syncing the same record twice is idempotent (upsert by id).
    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )

    # Denormalised collector name for easy reporting/export.
    collector_name = Column(String(255), nullable=False)

    # Step 1 — consent
    verbal_consent = Column(Boolean, nullable=False, default=False)
    # Contact phone (used to group siblings registered under one number).
    phone = Column(String(32), nullable=True, index=True)

    # Step 2 — about the child
    child_name = Column(String(255), nullable=True)
    child_age = Column(Integer, nullable=True)           # years
    child_age_months = Column(Integer, nullable=True)    # 0–11, in addition to years
    child_sex = Column(String(20), nullable=True)        # male / female / other
    responder = Column(String(20), nullable=True)        # father / mother / other
    responder_other = Column(String(255), nullable=True)  # free text when "other"

    # Step 4 — medical record
    medical_record = Column(Boolean, nullable=True)            # has a medical record
    medical_record_photo = Column(String(255), nullable=True)  # uploaded photo
    vaccines = Column(String(64), nullable=True)               # CSV: opv,ipv,none

    # Location captured when the collection was started
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    location_address = Column(String(512), nullable=True)

    # Payout tracking: false until the admin marks this entry as paid.
    paid = Column(Boolean, nullable=False, default=False, index=True)

    # Client timestamp (when it was actually collected, possibly offline)
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)
    # Server timestamp (when it reached the backend)
    synced_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="collections")
    answers = relationship(
        "Answer", back_populates="collection", cascade="all, delete-orphan"
    )


class Question(Base):
    """An admin-managed screening question rendered dynamically by the app."""
    __tablename__ = "questions"

    id = Column(String(36), primary_key=True, default=_uuid)
    code = Column(String(64), unique=True, index=True, nullable=False)
    order_index = Column(Integer, nullable=False, default=0)
    title = Column(String(512), nullable=False)
    help_text = Column(String(1024), nullable=True)

    # yes_no | single_choice | multi_choice | number | text
    qtype = Column(String(20), nullable=False, default="yes_no")
    options_json = Column(Text, nullable=True)  # JSON array for choice types

    required = Column(Boolean, nullable=False, default=True)
    secondary_aim = Column(Boolean, nullable=False, default=False)
    # For yes_no: when answered "yes", prompt for a photo / a note.
    photo_on_yes = Column(Boolean, nullable=False, default=False)
    note_on_yes = Column(Boolean, nullable=False, default=False)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Answer(Base):
    """One collector's answer to one question, attached to a collection."""
    __tablename__ = "answers"

    id = Column(String(36), primary_key=True, default=_uuid)
    collection_id = Column(
        String(36), ForeignKey("collections.id"), index=True, nullable=False
    )
    question_id = Column(String(36), nullable=True)  # null if question removed
    question_code = Column(String(64), nullable=False)
    question_title = Column(String(512), nullable=True)  # snapshot at answer time
    qtype = Column(String(20), nullable=True)

    value_bool = Column(Boolean, nullable=True)
    value_number = Column(Float, nullable=True)
    value_text = Column(Text, nullable=True)   # text / note / joined multi-choice
    photo_filename = Column(String(255), nullable=True)

    collection = relationship("Collection", back_populates="answers")


class Setting(Base):
    """Simple key/value store for admin-configurable settings (payment rates)."""
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(String(255), nullable=True)


class Payout(Base):
    """A recorded payment to a collector. Created when an admin marks them paid;
    it freezes how many entries were settled so the app can show the receipt and
    the 'due' counter resets to zero."""
    __tablename__ = "payouts"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    amount = Column(Float, nullable=False, default=0)
    entries_count = Column(Integer, nullable=False, default=0)
    per_entry = Column(Float, nullable=False, default=0)
    training_included = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class CollectorGroup(Base):
    """An admin-defined group of collectors, for filtered reporting."""
    __tablename__ = "collector_groups"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship(
        "User", secondary=group_members, back_populates="groups"
    )
