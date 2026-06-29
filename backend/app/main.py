"""UsmleWise CRIST API entrypoint."""
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from . import models, schemas
from .auth import get_current_user
from .config import settings
from .database import Base, engine
from .routers import (
    admin_router,
    auth_router,
    collections_router,
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

# Mobile clients don't need CORS, but this keeps a web dashboard option open.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def no_cache_dashboard(request, call_next):
    """Keep the admin dashboard and web app from being aggressively cached, so
    deploys show up on a normal refresh instead of needing a hard refresh."""
    response = await call_next(request)
    if request.url.path.startswith(("/admin", "/web")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


app.include_router(auth_router.router)
app.include_router(collections_router.router)
app.include_router(stats_router.router)
app.include_router(admin_router.router)  # /api/* admin endpoints
app.include_router(questions_router.router)  # /api/questions admin CRUD
app.include_router(questions_router.public_router)  # /questionnaire (collector)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME}


_LEGAL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "legal")
)


def _legal_page(name: str):
    path = os.path.join(_LEGAL_DIR, name)
    if not os.path.isfile(path):
        return {"detail": "Not found"}
    return FileResponse(path, media_type="text/html")


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
