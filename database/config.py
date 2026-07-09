"""
database/config.py
------------------
Loads database connection parameters from the .env file and builds
the SQLAlchemy engine with a connection pool.
"""

import logging
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load .env from the project root (two levels up from this file)
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(_ENV_PATH)


class ConfigurationError(Exception):
    """Raised when a required database configuration value is missing."""
    pass


def _get_required(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ConfigurationError(
            f"Missing required environment variable: '{key}'. "
            f"Check your .env file."
        )
    return value


def get_database_url() -> str:
    host     = _get_required("DB_HOST")
    port     = _get_required("DB_PORT")
    name     = _get_required("DB_NAME")
    user     = _get_required("DB_USER")
    password = _get_required("DB_PASSWORD")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


# SQLAlchemy engine — pool_size 1–5 as per requirements
engine = None
SessionLocal = None


def init_engine():
    """Initialize the SQLAlchemy engine and session factory."""
    global engine, SessionLocal
    url = get_database_url()
    engine = create_engine(
        url,
        pool_size=5,
        max_overflow=0,
        pool_pre_ping=True,   # verify connection before using it
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return engine


def verify_connection() -> bool:
    """
    Try to open a connection and run a trivial query.
    Returns True on success, False on failure (graceful degradation).
    """
    _logger = logging.getLogger(__name__)
    try:
        eng = init_engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        _logger.info("Database connection successful.")
        return True
    except ConfigurationError as e:
        _logger.error(f"Configuration error: {e}")
        return False
    except Exception as e:
        _logger.error(f"Database connection failed: {e}")
        return False


if __name__ == "__main__":
    verify_connection()
