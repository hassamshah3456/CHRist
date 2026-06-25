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
)
from sqlalchemy.orm import relationship

from .database import Base


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

    created_at = Column(DateTime, default=datetime.utcnow)

    collections = relationship("Collection", back_populates="user")


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

    # Step 2 — about the child
    child_age = Column(Integer, nullable=True)
    child_sex = Column(String(20), nullable=True)        # male / female / other
    responder = Column(String(20), nullable=True)        # father / mother / other
    responder_other = Column(String(255), nullable=True)  # free text when "other"

    # Location captured when the collection was started
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    location_address = Column(String(512), nullable=True)

    # Client timestamp (when it was actually collected, possibly offline)
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)
    # Server timestamp (when it reached the backend)
    synced_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="collections")
