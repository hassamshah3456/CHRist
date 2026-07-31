"""UsmleWise CRIST API entrypoint."""
import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from . import models, schemas
from .auth import get_current_user
from .config import settings, validate_production
from .database import Base, engine

# Abort start-up rather than run production on a placeholder signing key, an
# unencrypted media volume or a wildcard CORS policy. Deliberately the first
# thing that happens after imports, before any table is touched.
validate_production()

from .routers import (  # noqa: E402 — must follow the config gate above
    admin_router,
    auth_router,
    collections_router,
    omr_router,
    questions_router,
    stats_router,
)

# Create tables on startup (fine for SQLite / small deployments; for Postgres
# in production you'd typically use Alembic migrations instead).
Base.metadata.create_all(bind=engine)


def _ensure_columns():
    """Self-healing schema patch: add any model column missing from an existing
    table. create_all() never alters existing tables, so a database created by
    an older build can be missing columns added since (phone, child_name, the
    payment/medical fields, …). We derive the column list and types straight
    from the models, so this stays correct as the models evolve.

    DB-agnostic, idempotent, and tolerant of Gunicorn's multiple workers each
    importing this module at once.
    """
    # NOT NULL columns get a default so existing rows backfill cleanly; others
    # are added nullable (safe for backfilling an already-populated table).
    not_null_defaults = {
        "paid": "0",
        "card_submitted": "0",
        "card_approved": "0",
        "training_paid": "0",
        "app_seconds": "0",
        "card_entries_count": "0",
        "card_per_entry": "0",
        # Security columns added with the HIPAA safeguards. Existing rows
        # backfill to "never revoked, no failures, MFA off", which is the
        # correct starting state for an account that predates them.
        "token_version": "0",
        "failed_login_count": "0",
        "mfa_enabled": "0",
        "subject_count": "1",
        "success": "1",
    }
    inspector = inspect(engine)
    prep = engine.dialect.identifier_preparer
    for table_name, table in Base.metadata.tables.items():
        try:
            existing = {c["name"] for c in inspector.get_columns(table_name)}
        except Exception:
            continue  # table absent; create_all() handles fresh installs
        for col in table.columns:
            if col.name in existing:
                continue
            try:
                coltype = col.type.compile(dialect=engine.dialect)
            except Exception:
                continue
            if col.name in not_null_defaults:
                tail = f" NOT NULL DEFAULT {not_null_defaults[col.name]}"
            else:
                tail = " NULL"  # backfill existing rows with NULL
            ddl = (
                f"ALTER TABLE {prep.quote(table_name)} "
                f"ADD COLUMN {prep.quote(col.name)} {coltype}{tail}"
            )
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
            except Exception:
                # Already added (e.g. another worker won the race) — ignore.
                pass


_ensure_columns()


def _widen_settings_value():
    """instructions HTML exceeds VARCHAR(255); widen settings.value to TEXT."""
    dialect = engine.dialect.name
    try:
        with engine.begin() as conn:
            if dialect == "mysql":
                conn.execute(text(
                    "ALTER TABLE settings MODIFY COLUMN value TEXT NULL"
                ))
            elif dialect == "postgresql":
                conn.execute(text(
                    "ALTER TABLE settings ALTER COLUMN value TYPE TEXT"
                ))
    except Exception:
        pass


def _relax_user_email_nullable():
    """Collectors no longer require email; admins still use it."""
    dialect = engine.dialect.name
    try:
        with engine.begin() as conn:
            if dialect == "mysql":
                conn.execute(text(
                    "ALTER TABLE users MODIFY COLUMN email "
                    "VARCHAR(255) NULL"
                ))
            elif dialect == "postgresql":
                conn.execute(text(
                    "ALTER TABLE users ALTER COLUMN email DROP NOT NULL"
                ))
    except Exception:
        pass


def _widen_answer_question_id():
    """Follow-up answers use parent UUID + '__fu' (40 chars); widen column."""
    dialect = engine.dialect.name
    try:
        with engine.begin() as conn:
            if dialect == "mysql":
                conn.execute(text(
                    "ALTER TABLE answers MODIFY COLUMN question_id "
                    "VARCHAR(64) NULL"
                ))
            elif dialect == "postgresql":
                conn.execute(text(
                    "ALTER TABLE answers ALTER COLUMN question_id "
                    "TYPE VARCHAR(64)"
                ))
    except Exception:
        pass


_widen_settings_value()
_relax_user_email_nullable()
_widen_answer_question_id()

try:
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE collections SET card_submitted = 1 "
            "WHERE medical_record_photo IS NOT NULL "
            "AND medical_record_photo != '' "
            "AND card_submitted = 0"
        ))
except Exception:
    pass

# Ensure the media directory exists for uploaded photos.
os.makedirs(settings.MEDIA_DIR, exist_ok=True)

app = FastAPI(title=settings.PROJECT_NAME)

# CORS is off by default. Native mobile clients do not use it, and the admin
# dashboard is served from this same origin, so no cross-origin access is
# needed. Previously this was allow_origins=["*"] with allow_credentials=True,
# which let any website on the internet script authenticated calls against the
# API using a signed-in administrator's browser session. Set ALLOWED_ORIGINS
# only if a separately hosted front end genuinely needs access.
if settings.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def security_headers(request, call_next):
    """Baseline hardening headers, plus cache rules for PHI-bearing responses.

    The API returns participant data as JSON; without an explicit no-store it
    can be written to a shared proxy cache or left in a browser's back/forward
    cache on a device that several collectors use.
    """
    response = await call_next(request)
    path = request.url.path

    # Never let the browser guess a content type, be framed, or leak the full
    # URL (which can carry record ids) to third-party sites.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "geolocation=(self), camera=(self), microphone=()"
    )

    # HSTS only in production: sending it from a local http:// dev server
    # would pin the browser to https for localhost and break development.
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    # Keep the dashboard and web app from being aggressively cached, so deploys
    # show up on a normal refresh instead of needing a hard refresh.
    if path.startswith(("/admin", "/web")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    # API responses carrying participant data must not be cached at all.
    elif path.startswith(("/api", "/collections", "/auth", "/me", "/stats")):
        response.headers.setdefault("Cache-Control", "no-store, private")

    return response


app.include_router(auth_router.router)
app.include_router(collections_router.router)
app.include_router(stats_router.router)
app.include_router(admin_router.router)  # /api/* admin endpoints
app.include_router(omr_router.router)  # /api/omr/* + /api/ai/* (scanned sheets)
app.include_router(questions_router.router)  # /api/questions admin CRUD
app.include_router(questions_router.public_router)  # /questionnaire (collector)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME}


_LEGAL_DIRS = [
    # Bundled with the app package (Docker / production).
    os.path.join(os.path.dirname(__file__), "legal"),
    # Repo-root copy when running from a full checkout.
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "legal")),
]


def _legal_page(name: str):
    for base in _LEGAL_DIRS:
        path = os.path.join(base, name)
        if os.path.isfile(path):
            return FileResponse(path, media_type="text/html")
    raise HTTPException(status_code=404, detail="Page not found")


@app.get("/privacy", include_in_schema=False)
def privacy_policy():
    """Public privacy policy (linked from Google Play listing and the app)."""
    return _legal_page("privacy.html")


@app.get("/terms", include_in_schema=False)
def terms_of_use():
    """Public terms of use."""
    return _legal_page("terms.html")


@app.get("/delete-account", include_in_schema=False)
def delete_account_page():
    """Public account deletion instructions (Google Play data deletion URL)."""
    return _legal_page("delete-account.html")


# Common alternate paths (e.g. Play Console, old bookmarks).
@app.get("/legal/privacy", include_in_schema=False)
def privacy_policy_alias():
    return _legal_page("privacy.html")


@app.get("/legal/terms", include_in_schema=False)
def terms_of_use_alias():
    return _legal_page("terms.html")


@app.get("/legal/delete-account", include_in_schema=False)
def delete_account_page_alias():
    return _legal_page("delete-account.html")


@app.get("/me", response_model=schemas.UserOut, tags=["auth"])
def me(user: models.User = Depends(get_current_user)):
    return user


# ---- Web dashboard (static SPA) served at /admin ----
# API routes above are registered first, so /api/* always resolves to the API;
# everything under /admin/* falls through to these static files.
_DASHBOARD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..",
    "dashboard",
)
_DASHBOARD_DIR = os.path.abspath(_DASHBOARD_DIR)

if os.path.isdir(_DASHBOARD_DIR):
    app.mount(
        "/admin",
        StaticFiles(directory=_DASHBOARD_DIR, html=True),
        name="dashboard",
    )

# ---- Collector web app (Flutter web build) served at /web ----
_WEB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "build", "web")
)
if os.path.isdir(_WEB_DIR):
    app.mount(
        "/web",
        StaticFiles(directory=_WEB_DIR, html=True),
        name="webapp",
    )

if os.path.isdir(_DASHBOARD_DIR):

    @app.get("/", include_in_schema=False)
    def root_redirect():
        return RedirectResponse(url="/admin/")
else:
    @app.get("/", tags=["health"])
    def root():
        return {"status": "ok", "service": settings.PROJECT_NAME}
