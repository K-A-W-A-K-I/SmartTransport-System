import logging
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy import text

from database.config import init_engine

logger = logging.getLogger(__name__)


def get_engine():
    return init_engine()


def get_watermark(pipeline_name: str = "main") -> datetime | None:
    """
    Return the last successful ETL run timestamp for this pipeline.
    Returns None if this is the first run.
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT last_run_at FROM etl_watermark WHERE pipeline_name = :name"),
            {"name": pipeline_name}
        ).fetchone()
    if row:
        logger.info(f"Watermark found: {row[0]}")
        return row[0]
    logger.info("No watermark found — first run, extracting all data.")
    return None


def extract_events(since: datetime | None = None) -> pd.DataFrame:
    """
    Read passenger_events from the database.

    Args:
        since: only return events with timestamp > since.
               If None, return all events.

    Returns:
        DataFrame with columns:
            id, session_id, bus_id, station_id, direction,
            timestamp, occupancy_after_event, occupancy_rate
    """
    engine = get_engine()

    if since is not None:
        query = text("""
            SELECT
                pe.id,
                pe.session_id,
                pe.bus_id,
                pe.station_id,
                pe.direction,
                pe.timestamp,
                pe.occupancy_after_event,
                pe.occupancy_rate,
                s.bus_id  AS session_bus_id
            FROM passenger_events pe
            LEFT JOIN sessions s ON s.id = pe.session_id
            WHERE pe.timestamp > :since
            ORDER BY pe.timestamp
        """)
        params = {"since": since}
    else:
        query = text("""
            SELECT
                pe.id,
                pe.session_id,
                pe.bus_id,
                pe.station_id,
                pe.direction,
                pe.timestamp,
                pe.occupancy_after_event,
                pe.occupancy_rate,
                s.bus_id  AS session_bus_id
            FROM passenger_events pe
            LEFT JOIN sessions s ON s.id = pe.session_id
            ORDER BY pe.timestamp
        """)
        params = {}

    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=params)

    # Resolve bus_id: prefer pe.bus_id, fall back to session's bus_id
    df["bus_id"] = df["bus_id"].combine_first(df["session_bus_id"])
    df = df.drop(columns=["session_bus_id"])

    logger.info(f"Extracted {len(df)} passenger_events rows.")
    return df


def extract_buses() -> pd.DataFrame:
    """Return all buses with their line_id and capacity."""
    engine = get_engine()
    query = text("SELECT bus_id, capacity, line_id FROM buses")
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    logger.info(f"Extracted {len(df)} buses.")
    return df


def extract_lines() -> pd.DataFrame:
    """Return all lines."""
    engine = get_engine()
    query = text("SELECT line_id, line_name, line_number FROM lines")
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    logger.info(f"Extracted {len(df)} lines.")
    return df


def extract_tickets(since: datetime | None = None) -> pd.DataFrame:
    """
    Read ticket_sales rows from the database.

    ticket_sales is manually entered — we read all of it (or since
    the watermark) and aggregate it into ticket_stats in the transform step.

    Returns:
        DataFrame with columns:
            id, bus_id, line_id, station_id, timestamp, tickets_sold, entered_by
    """
    engine = get_engine()

    if since is not None:
        query = text("""
            SELECT id, bus_id, line_id, station_id,
                   timestamp, tickets_sold, entered_by
            FROM ticket_sales
            WHERE timestamp > :since
            ORDER BY timestamp
        """)
        params = {"since": since}
    else:
        query = text("""
            SELECT id, bus_id, line_id, station_id,
                   timestamp, tickets_sold, entered_by
            FROM ticket_sales
            ORDER BY timestamp
        """)
        params = {}

    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=params)

    logger.info(f"Extracted {len(df)} ticket_sales rows.")
    return df


def extract_all(pipeline_name: str = "main") -> dict:
    """
    Full extract step. Returns a dict of DataFrames and the watermark.

    Returns:
        {
            "events":    DataFrame of raw passenger events,
            "buses":     DataFrame of bus master data,
            "lines":     DataFrame of line master data,
            "tickets":   DataFrame of ticket_sales rows,
            "watermark": datetime | None
        }
    """
    watermark = get_watermark(pipeline_name)
    events    = extract_events(since=watermark)
    buses     = extract_buses()
    lines     = extract_lines()
    tickets   = extract_tickets(since=watermark)

    return {
        "events":    events,
        "buses":     buses,
        "lines":     lines,
        "tickets":   tickets,
        "watermark": watermark,
    }
