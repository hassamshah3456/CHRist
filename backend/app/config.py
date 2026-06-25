"""Application configuration loaded from environment variables.

Defaults are dev-friendly (SQLite, throwaway secret). In production set
DATABASE_URL (e.g. a Postgres URL) and SECRET_KEY via real environment vars.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env explicitly (robust regardless of CWD or how Python is
# invoked). config.py lives in backend/app/, so the .env is one level up.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    # Database connection string. Default: local SQLite file.
    # Remote MySQL:
    #   mysql+pymysql://USER:PASSWORD@HOST:3306/DBNAME
    #   mysql+pymysql://USER:PASSWORD@HOST:3306/DBNAME?ssl_ca=/path/ca.pem  (TLS)
    # Postgres:
    #   postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME
    # IMPORTANT: set this via a server environment variable, never in code/git.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./usmlewise.db")

    # JWT signing secret. MUST be overridden in production.
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-please")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    # Tokens are long-lived because field collectors may stay offline for days.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 30))  # 30 days
    )

    PROJECT_NAME: str = "UsmleWise CHRIST API"


settings = Settings()
