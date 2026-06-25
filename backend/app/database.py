"""SQLAlchemy engine, session factory and declarative base."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

# check_same_thread is only needed for SQLite.
is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

# For MySQL/Postgres, pool_pre_ping avoids "MySQL server has gone away" errors
# by checking connections before use; pool_recycle drops connections older than
# the server's idle timeout (MySQL defaults to 8 hours).
engine_kwargs = {} if is_sqlite else {"pool_pre_ping": True, "pool_recycle": 280}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
