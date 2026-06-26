"""UsmleWise CRIST API entrypoint."""
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
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
    """Keep the admin dashboard from being aggressively cached, so deploys
    show up on a normal refresh instead of needing a hard refresh."""
    response = await call_next(request)
    if request.url.path.startswith("/admin"):
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

    @app.get("/", include_in_schema=False)
    def root_redirect():
        return RedirectResponse(url="/admin/")
else:
    @app.get("/", tags=["health"])
    def root():
        return {"status": "ok", "service": settings.PROJECT_NAME}
