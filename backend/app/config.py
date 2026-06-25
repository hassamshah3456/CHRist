"""Application configuration loaded from environment variables.

Defaults are dev-friendly (SQLite, throwaway secret). In production set
DATABASE_URL (e.g. a Postgres URL) and SECRET_KEY via real environment vars.
"""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Database. Default: local SQLite file. For Postgres use e.g.
    #   postgresql+psycopg2://user:pass@host:5432/dbname
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
