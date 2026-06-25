"""UsmleWise CHRIST API entrypoint."""
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

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
