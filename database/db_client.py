"""
database/db_client.py
---------------------
Low-level database access functions.
Handles connection lifecycle, raw inserts, and graceful error handling.

All business logic lives in session_service.py — not here.
This module only speaks to the database.
"""

import logging
from contextlib import contextmanager
from sqlalchemy.orm import Session as OrmSession

from database.config import init_engine, ConfigurationError
from database.models import Base, Session as SessionModel, PassengerEvent, Bus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engine / schema bootstrap
# ---------------------------------------------------------------------------

def get_engine():
    """Return an initialised SQLAlchemy engine."""
    return init_engine()


def create_tables():
    """
    Create all tables that do not yet exist.
    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS internally).
    """
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("Tables verified / created.")


# ---------------------------------------------------------------------------
# Connection context manager
# ---------------------------------------------------------------------------

@contextmanager
def get_session():
    """
    Yield a SQLAlchemy ORM session.
    Commits on success, rolls back on any exception, always closes.

    Usage:
        with get_session() as db:
            db.add(some_object)
    """
    engine = get_engine()
    db: OrmSession = OrmSession(engine)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Session inserts
# ---------------------------------------------------------------------------

def insert_session(session_data: dict) -> int | None:
    """
    Insert one row into the `sessions` table.

    Args:
        session_data: dict with keys matching Session model columns:
            session_start, session_end, mode, video_file,
            entry_count, exit_count

    Returns:
        The new row's id on success, None on failure.
    """
    try:
        with get_session() as db:
            record = SessionModel(**session_data)
            db.add(record)
            db.flush()          # populate record.id before commit
            new_id = record.id
        logger.info(f"Session inserted with id={new_id}")
        return new_id
    except ConfigurationError as e:
        logger.error(f"DB config error — session not saved: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to insert session: {e}")
        return None


def update_session(session_id: int, updates: dict) -> bool:
    """
    Update columns on an existing session row.

    Args:
        session_id: id of the row to update.
        updates:    dict of column names → new values.

    Returns:
        True on success, False on failure.
    """
    try:
        with get_session() as db:
            record = db.get(SessionModel, session_id)
            if record is None:
                logger.error(f"Session id={session_id} not found for update.")
                return False
            for key, value in updates.items():
                setattr(record, key, value)
        logger.info(f"Session id={session_id} updated: {list(updates.keys())}")
        return True
    except Exception as e:
        logger.error(f"Failed to update session id={session_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Passenger event inserts
# ---------------------------------------------------------------------------

def insert_event(event_data: dict) -> int | None:
    """
    Insert one row into the `passenger_events` table.

    Args:
        event_data: dict with keys matching PassengerEvent model columns:
            session_id, timestamp, direction, occupancy_after_event,
            station_id (optional), bus_id (optional)

    Returns:
        The new row's id on success, None on failure.
    """
    try:
        with get_session() as db:
            event = PassengerEvent(**event_data)
            db.add(event)
            db.flush()
            new_id = event.id
        logger.info(f"PassengerEvent inserted with id={new_id}")
        return new_id
    except Exception as e:
        logger.error(f"Failed to insert passenger event: {e}")
        return None


def insert_events_bulk(events: list[dict]) -> int:
    """
    Insert multiple passenger events in a single transaction.

    Args:
        events: list of dicts, each matching PassengerEvent columns.

    Returns:
        Number of rows successfully inserted (0 on failure).
    """
    if not events:
        return 0
    try:
        with get_session() as db:
            db.bulk_insert_mappings(PassengerEvent, events)
        logger.info(f"Bulk inserted {len(events)} passenger events.")
        return len(events)
    except Exception as e:
        logger.error(f"Bulk insert failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Bus queries
# ---------------------------------------------------------------------------

def get_bus_capacity(bus_id: int) -> int | None:
    """
    Return the capacity of a bus by id.
    Called once per session at start() — result is cached in SessionService.

    Returns:
        The bus capacity, or None if the bus is not found.
    """
    try:
        with get_session() as db:
            bus = db.get(Bus, bus_id)
            if bus is None:
                logger.warning(f"Bus id={bus_id} not found.")
                return None
            return bus.capacity
    except Exception as e:
        logger.error(f"Failed to fetch bus capacity for bus_id={bus_id}: {e}")
        return None
