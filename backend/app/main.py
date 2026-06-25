"""UsmleWise CHRIST API entrypoint."""
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models, schemas
from .auth import get_current_user
from .config import settings
from .database import Base, engine
from .routers import auth_router, collections_router, stats_router

# Create tables on startup (fine for SQLite / small deployments; for Postgres
# in production you'd typically use Alembic migrations instead).
Base.metadata.create_all(bind=engine)

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


@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME}


@app.get("/me", response_model=schemas.UserOut, tags=["auth"])
def me(user: models.User = Depends(get_current_user)):
    return user
