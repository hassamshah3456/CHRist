"""PHI access audit trail — HIPAA §164.312(b) (Audit controls).

The rule requires "hardware, software, and/or procedural mechanisms that record
and examine activity in information systems that contain or use electronic
protected health information". Before this module the system had none: an
administrator could open every child's record, view medical-record photographs
and export the whole study to CSV without leaving a trace.

Design notes
------------
* **Append-only by convention and by API.** There is no update or delete path
  in the application. Records are pruned only by the retention job, which
  refuses to touch anything younger than the configured window.
* **Never records PHI itself.** An audit row identifies *which* record was
  touched, not what it said. Otherwise the audit log becomes a second, less
  protected copy of the data it exists to protect.
* **Failures never break the request.** A dropped audit row is bad; a
  clinician-facing 500 because the audit table was briefly unavailable is
  worse. Failures are logged loudly and the request proceeds.
* **Own transaction.** Audit writes commit independently of the business
  transaction, so a rolled-back request still leaves evidence of the attempt.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .database import SessionLocal

logger = logging.getLogger(__name__)


# ---- Action vocabulary ---------------------------------------------------
# Kept small and stable so the log stays queryable. Anything that reveals,
# copies or destroys PHI belongs here.
class Action:
    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILURE = "login.failure"
    LOGIN_LOCKED = "login.locked"
    LOGOUT = "logout"
    MFA_ENROLLED = "mfa.enrolled"
    MFA_FAILURE = "mfa.failure"

    # PHI creation (by the collector in the field)
    SYNC_COLLECTIONS = "phi.sync_collections"      # records uploaded from a device
    UPLOAD_PHOTO = "phi.upload_photo"              # medical-record image stored

    # PHI reads
    VIEW_COLLECTIONS = "phi.view_collections"      # list of participant records
    VIEW_COLLECTION = "phi.view_collection"        # a single record
    VIEW_PHOTO = "phi.view_photo"                  # medical-record image
    VIEW_MAP = "phi.view_map"                      # geo-located participants
    VIEW_COLLECTOR = "phi.view_collector"          # one collector's submissions
    VIEW_OMR = "phi.view_omr"                      # scanned paper sheet

    # PHI leaving the perimeter
    EXPORT_CSV = "phi.export_csv"
    EXPORT_CSV_DEIDENTIFIED = "phi.export_csv_deidentified"
    AI_DISCLOSURE = "phi.disclose_to_ai_processor"

    # PHI mutations
    DELETE_COLLECTION = "phi.delete_collection"
    DELETE_ACCOUNT = "phi.delete_account"
    UPDATE_COLLECTOR = "phi.update_collector"

    # Configuration changes worth knowing about
    SETTINGS_CHANGED = "admin.settings_changed"
    AI_CONFIG_CHANGED = "admin.ai_config_changed"


def client_ip(request: Optional[Request]) -> Optional[str]:
    """Best-effort caller IP, honouring one layer of reverse proxy.

    Render, Railway and most PaaS hosts terminate TLS in front of the app, so
    request.client.host is the proxy. X-Forwarded-For's first entry is the
    original client. This is advisory only — the header is caller-controlled
    and must never be used for authorisation.
    """
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


def record(
    *,
    actor_id: Optional[str],
    actor_name: Optional[str] = None,
    actor_role: Optional[str] = None,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    subject_count: int = 1,
    detail: Optional[str] = None,
    request: Optional[Request] = None,
    success: bool = True,
) -> None:
    """Write one audit row in its own transaction.

    `subject_count` matters for breach assessment: an export touching 4,000
    participants is a materially different event from opening one record, and
    the Breach Notification Rule's thresholds are counted in individuals.
    """
    db: Session = SessionLocal()
    try:
        db.add(models.AuditLog(
            actor_id=actor_id,
            actor_name=(actor_name or "")[:255] or None,
            actor_role=actor_role,
            action=action[:64],
            resource_type=(resource_type or "")[:32] or None,
            resource_id=(resource_id or "")[:64] or None,
            subject_count=max(0, int(subject_count or 0)),
            detail=(detail or "")[:512] or None,
            ip_address=client_ip(request),
            user_agent=(
                request.headers.get("user-agent", "")[:255] if request else None
            ) or None,
            success=bool(success),
            created_at=datetime.utcnow(),
        ))
        db.commit()
    except Exception:
        db.rollback()
        # Deliberately swallowed: see module docstring.
        logger.exception(
            "AUDIT WRITE FAILED action=%s actor=%s resource=%s/%s",
            action, actor_id, resource_type, resource_id,
        )
    finally:
        db.close()


def record_user(
    user: Optional[models.User],
    action: str,
    *,
    request: Optional[Request] = None,
    **kwargs,
) -> None:
    """Convenience wrapper for the common "an authenticated user did X" case."""
    record(
        actor_id=user.id if user else None,
        actor_name=user.name if user else None,
        actor_role=("admin" if user.is_admin else "collector") if user else None,
        action=action,
        request=request,
        **kwargs,
    )


def purge_expired(db: Session) -> int:
    """Delete audit rows past the retention window (default six years).

    §164.316(b)(2)(i) sets six years as the *minimum*; this never deletes
    anything younger, and refuses to run at all if misconfigured to a short
    window, so a stray environment variable cannot quietly destroy the trail.
    """
    days = settings.AUDIT_RETENTION_DAYS
    if days < 2190:
        raise ValueError(
            f"AUDIT_RETENTION_DAYS={days} is below the six-year (2190 day) "
            "HIPAA minimum; refusing to purge."
        )
    cutoff = datetime.utcnow() - timedelta(days=days)
    deleted = db.query(models.AuditLog).filter(
        models.AuditLog.created_at < cutoff
    ).delete(synchronize_session=False)
    db.commit()
    return deleted
