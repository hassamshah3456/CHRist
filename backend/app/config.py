"""Application configuration loaded from environment variables.

Security posture: defaults are dev-friendly (SQLite, throwaway secret) but the
application REFUSES TO START in production with an insecure configuration.
See `validate_production()` — it is called from main.py at import time.
"""
import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env explicitly (robust regardless of CWD or how Python is
# invoked). config.py lives in backend/app/, so the .env is one level up.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv_list(name: str, default: str = "") -> list:
    raw = os.getenv(name, default) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


# The placeholder shipped in .env.example. Treated as "no secret set at all".
INSECURE_SECRET = "change-me-in-production-please"


class Settings:
    # ---- Environment -----------------------------------------------------
    # "production" turns on the full set of safety checks. Anything else
    # (development, test) keeps the convenient defaults.
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").strip().lower()

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    # ---- Database --------------------------------------------------------
    # Remote MySQL:
    #   mysql+pymysql://USER:PASSWORD@HOST:3306/DBNAME
    #   mysql+pymysql://USER:PASSWORD@HOST:3306/DBNAME?ssl_ca=/path/ca.pem (TLS)
    # Postgres:
    #   postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME
    # IMPORTANT: set this via a server environment variable, never in code/git.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./usmlewise.db")

    # ---- JWT / sessions --------------------------------------------------
    SECRET_KEY: str = os.getenv("SECRET_KEY", INSECURE_SECRET)
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")

    # Collector tokens are long-lived by necessity: field workers stay offline
    # for days and must not be logged out mid-survey. HIPAA's automatic-logoff
    # safeguard is satisfied on the device instead — the app re-locks after
    # IDLE_LOCK_MINUTES of inactivity and requires the password again.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7))  # 7 days
    )
    # Admin sessions reach ALL participants' PHI, so they expire quickly.
    ADMIN_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ADMIN_TOKEN_EXPIRE_MINUTES", "60")
    )
    # Device-side inactivity lock (minutes), pushed to the app at login.
    IDLE_LOCK_MINUTES: int = int(os.getenv("IDLE_LOCK_MINUTES", "15"))

    # ---- Brute-force protection -----------------------------------------
    MAX_LOGIN_ATTEMPTS: int = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
    LOCKOUT_MINUTES: int = int(os.getenv("LOCKOUT_MINUTES", "15"))
    MIN_PASSWORD_LENGTH: int = int(os.getenv("MIN_PASSWORD_LENGTH", "10"))

    # ---- Multi-factor authentication ------------------------------------
    # Admin accounts hold the keys to every participant record. MFA is on by
    # default in production; an admin without MFA enrolled is prompted to
    # enrol on next sign-in rather than being locked out.
    REQUIRE_ADMIN_MFA: bool = _bool("REQUIRE_ADMIN_MFA", True)
    MFA_ISSUER: str = os.getenv("MFA_ISSUER", "CRIST Tool")

    # ---- CORS ------------------------------------------------------------
    # The dashboard is served same-origin, so this is normally empty. Add an
    # origin only if a separately hosted front end genuinely needs access.
    # A wildcard is rejected in production.
    ALLOWED_ORIGINS: list = _csv_list("ALLOWED_ORIGINS", "")

    # ---- Media (medical-record photographs) ------------------------------
    # Uploaded photos are encrypted at rest with AES-256-GCM. The key is a
    # base64-encoded 32-byte value held only in the server environment.
    # Generate:
    #   python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
    MEDIA_DIR: str = os.getenv(
        "MEDIA_DIR",
        str(Path(__file__).resolve().parent.parent / "media"),
    )
    MEDIA_ENCRYPTION_KEY: str = os.getenv("MEDIA_ENCRYPTION_KEY", "").strip()

    # ---- Audit -----------------------------------------------------------
    # §164.316(b)(2)(i): retain documentation for six years.
    AUDIT_RETENTION_DAYS: int = int(os.getenv("AUDIT_RETENTION_DAYS", "2190"))

    PROJECT_NAME: str = "CRIST Tool API"


settings = Settings()


def _fail(problems: list) -> None:
    banner = "=" * 72
    print(banner, file=sys.stderr)
    print("REFUSING TO START — insecure production configuration", file=sys.stderr)
    print(banner, file=sys.stderr)
    for p in problems:
        print(f"  * {p}", file=sys.stderr)
    print(banner, file=sys.stderr)
    raise SystemExit(1)


def validate_production() -> None:
    """Abort start-up if production is configured insecurely.

    A silent fallback to a known signing key or an unencrypted media volume is
    exactly the sort of misconfiguration that turns into a reportable breach,
    so these are hard failures rather than warnings.
    """
    if not settings.is_production:
        return

    problems = []

    if not settings.SECRET_KEY or settings.SECRET_KEY == INSECURE_SECRET:
        problems.append(
            "SECRET_KEY is unset or still the placeholder. Generate one with: "
            'python -c "import secrets; print(secrets.token_hex(32))"'
        )
    elif len(settings.SECRET_KEY) < 32:
        problems.append(
            f"SECRET_KEY is only {len(settings.SECRET_KEY)} characters; "
            "use at least 32."
        )

    if not settings.MEDIA_ENCRYPTION_KEY:
        problems.append(
            "MEDIA_ENCRYPTION_KEY is unset, so medical-record photographs "
            "would be written to disk unencrypted. Generate one with: "
            'python -c "import os,base64; '
            'print(base64.b64encode(os.urandom(32)).decode())"'
        )
    else:
        from .crypto import key_is_valid  # local import avoids a cycle
        if not key_is_valid(settings.MEDIA_ENCRYPTION_KEY):
            problems.append(
                "MEDIA_ENCRYPTION_KEY is not a base64-encoded 32-byte value."
            )

    if "*" in settings.ALLOWED_ORIGINS:
        problems.append(
            "ALLOWED_ORIGINS contains '*'. Name the dashboard origin "
            "explicitly, or leave it empty (the dashboard is same-origin)."
        )

    if settings.DATABASE_URL.startswith("sqlite"):
        problems.append(
            "DATABASE_URL still points at SQLite. Use a managed MySQL or "
            "PostgreSQL instance covered by a Business Associate Agreement."
        )

    if problems:
        _fail(problems)


def generate_secret() -> str:
    """Convenience used by manage.py."""
    return secrets.token_hex(32)
