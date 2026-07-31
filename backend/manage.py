"""Small management CLI.

Run from the backend/ directory, inside the venv.

    python manage.py create-admin --email you@example.com --password 'StrongPass1'
    python manage.py generate-secret          # JWT signing key
    python manage.py generate-media-key       # AES key for photo encryption
    python manage.py encrypt-media            # encrypt pre-existing photos
    python manage.py purge-audit              # drop audit rows past retention
    python manage.py revoke-sessions --email you@example.com
    python manage.py reset-mfa --email you@example.com
    python manage.py audit-report --days 7
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

from app import audit, crypto, models
from app.auth import enforce_password_policy, hash_password, password_problems
from app.config import generate_secret, settings
from app.database import Base, SessionLocal, engine


def create_admin(email: str, password: str, name: str) -> None:
    problems = password_problems(password)
    if problems:
        print("Refusing to set a weak admin password. It must "
              + ", and ".join(problems) + ".", file=sys.stderr)
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user:
            user.is_admin = True
            if password:
                user.password_hash = hash_password(password)
                user.password_changed_at = datetime.utcnow()
                # A password reset must invalidate any session opened with the
                # old one.
                user.token_version = int(user.token_version or 0) + 1
            db.commit()
            print(f"Promoted existing user to admin: {email}")
        else:
            user = models.User(
                name=name,
                email=email,
                password_hash=hash_password(password),
                password_changed_at=datetime.utcnow(),
                upi_address="-",  # admins aren't paid collectors
                is_admin=True,
            )
            db.add(user)
            db.commit()
            print(f"Created admin user: {email}")

        if settings.REQUIRE_ADMIN_MFA and not user.mfa_enabled:
            print(
                "\nNOTE: multi-factor authentication is required for admins.\n"
                "  Sign in at /admin — you will be prompted to scan a QR code\n"
                "  and enter a 6-digit code before any participant data loads."
            )
    finally:
        db.close()


def encrypt_media() -> None:
    """Encrypt photos written before encryption at rest was introduced.

    Idempotent: files already carrying the CRIST1 magic prefix are skipped, so
    this is safe to run repeatedly (e.g. from a deploy hook).
    """
    if not crypto.encryption_enabled():
        print("MEDIA_ENCRYPTION_KEY is not set — nothing to do.", file=sys.stderr)
        sys.exit(1)

    directory = settings.MEDIA_DIR
    if not os.path.isdir(directory):
        print(f"No media directory at {directory}.")
        return

    converted = skipped = failed = 0
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path) or name.endswith(".tmp"):
            continue
        try:
            with open(path, "rb") as fh:
                blob = fh.read()
            if crypto.is_encrypted(blob):
                skipped += 1
                continue
            crypto.write_encrypted(path, blob)
            converted += 1
        except Exception as exc:  # noqa: BLE001 — report and keep going
            failed += 1
            print(f"  FAILED {name}: {exc}", file=sys.stderr)

    print(f"Encrypted {converted}, already encrypted {skipped}, failed {failed}.")


def purge_audit() -> None:
    db = SessionLocal()
    try:
        deleted = audit.purge_expired(db)
        print(
            f"Deleted {deleted} audit rows older than "
            f"{settings.AUDIT_RETENTION_DAYS} days."
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


def _find_user(db, email: str):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        print(f"No user with email {email}.", file=sys.stderr)
        sys.exit(1)
    return user


def revoke_sessions(email: str) -> None:
    """Offboarding: kill every outstanding token for an account."""
    db = SessionLocal()
    try:
        user = _find_user(db, email)
        user.token_version = int(user.token_version or 0) + 1
        db.commit()
        audit.record_user(
            user, audit.Action.LOGOUT, subject_count=0,
            detail="all sessions revoked from the command line",
        )
        print(f"Revoked all sessions for {email}.")
    finally:
        db.close()


def reset_mfa(email: str) -> None:
    """Clear a lost authenticator so the admin can re-enrol on next sign-in."""
    db = SessionLocal()
    try:
        user = _find_user(db, email)
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_recovery_hashes = None
        user.token_version = int(user.token_version or 0) + 1
        db.commit()
        audit.record_user(
            user, audit.Action.MFA_ENROLLED, subject_count=0, success=False,
            detail="MFA reset from the command line; re-enrolment required",
        )
        print(f"MFA reset for {email}. They must re-enrol at next sign-in.")
    finally:
        db.close()


def audit_report(days: int) -> None:
    """The periodic information-system-activity review in one command."""
    since = datetime.utcnow() - timedelta(days=days)
    db = SessionLocal()
    try:
        rows = db.query(models.AuditLog).filter(
            models.AuditLog.created_at >= since
        ).all()
        if not rows:
            print(f"No audit activity in the last {days} days.")
            return

        by_action = {}
        for r in rows:
            by_action[r.action] = by_action.get(r.action, 0) + 1

        exported = sum(
            r.subject_count for r in rows if r.action.startswith("phi.export")
        )
        failures = [r for r in rows if not r.success]

        print(f"Audit review — last {days} days ({len(rows)} events)\n")
        for action, count in sorted(by_action.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>6}  {action}")
        print(f"\n  Individuals in CSV exports: {exported}")
        print(f"  Failed events: {len(failures)}")
        for r in failures[:20]:
            print(
                f"    {r.created_at:%Y-%m-%d %H:%M}  {r.action}  "
                f"{r.actor_name or 'unknown'}  {r.ip_address or '-'}  "
                f"{r.detail or ''}"
            )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UsmleWise CRIST management")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-admin", help="Create or promote an admin user")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--name", default="Administrator")

    sub.add_parser("generate-secret", help="Print a new JWT signing key")
    sub.add_parser("generate-media-key", help="Print a new media encryption key")
    sub.add_parser("encrypt-media", help="Encrypt photos stored before encryption")
    sub.add_parser("purge-audit", help="Delete audit rows past the retention window")

    p = sub.add_parser("revoke-sessions", help="Sign an account out everywhere")
    p.add_argument("--email", required=True)

    p = sub.add_parser("reset-mfa", help="Clear a lost authenticator")
    p.add_argument("--email", required=True)

    p = sub.add_parser("audit-report", help="Summarise recent audit activity")
    p.add_argument("--days", type=int, default=7)

    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args.email, args.password, args.name)
    elif args.command == "generate-secret":
        print(generate_secret())
    elif args.command == "generate-media-key":
        print(crypto.generate_key())
    elif args.command == "encrypt-media":
        encrypt_media()
    elif args.command == "purge-audit":
        purge_audit()
    elif args.command == "revoke-sessions":
        revoke_sessions(args.email)
    elif args.command == "reset-mfa":
        reset_mfa(args.email)
    elif args.command == "audit-report":
        audit_report(args.days)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
