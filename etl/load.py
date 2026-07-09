"""
etl/load.py
-----------
Writes aggregated DataFrames into the three analytics tables.

Responsibilities:
  - Upsert rows using INSERT ... ON CONFLICT DO UPDATE
  - Update the ETL watermark after a successful run
  - Log row counts and errors per table
  - Never crash the whole pipeline if one table fails

Nothing is computed here. Input is pure DataFrames from transform.py.
"""

import logging
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy import text

from database.config import init_engine

logger = logging.getLogger(__name__)


def get_engine():
    return init_engine()


# ---------------------------------------------------------------------------
# Individual table loaders
# ---------------------------------------------------------------------------

def load_hourly_station(df: pd.DataFrame) -> int:
    """
    Upsert into hourly_station_statistics.
    Natural key: (hour_start, station_id, line_id)
    Returns number of rows upserted.
    """
    if df.empty:
        logger.info("hourly_station_statistics: nothing to load.")
        return 0

    engine = get_engine()
    rows_loaded = 0

    try:
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(text("""
                    INSERT INTO hourly_station_statistics
                        (hour_start, station_id, line_id,
                         total_boardings, total_alightings,
                         avg_occupancy_rate,
                         hour, weekday, month, is_weekend,
                         updated_at)
                    VALUES
                        (:hour_start, :station_id, :line_id,
                         :total_boardings, :total_alightings,
                         :avg_occupancy_rate,
                         :hour, :weekday, :month, :is_weekend,
                         :updated_at)
                    ON CONFLICT (hour_start, station_id, COALESCE(line_id, -1))
                    DO UPDATE SET
                        total_boardings    = EXCLUDED.total_boardings,
                        total_alightings   = EXCLUDED.total_alightings,
                        avg_occupancy_rate = EXCLUDED.avg_occupancy_rate,
                        hour               = EXCLUDED.hour,
                        weekday            = EXCLUDED.weekday,
                        month              = EXCLUDED.month,
                        is_weekend         = EXCLUDED.is_weekend,
                        updated_at         = EXCLUDED.updated_at
                """), {
                    "hour_start":         row["hour_start"],
                    "station_id":         int(row["station_id"]) if pd.notna(row["station_id"]) else 1,
                    "line_id":            int(row["line_id"]) if pd.notna(row["line_id"]) else None,
                    "total_boardings":    int(row["total_boardings"]),
                    "total_alightings":   int(row["total_alightings"]),
                    "avg_occupancy_rate": float(row["avg_occupancy_rate"]) if pd.notna(row["avg_occupancy_rate"]) else None,
                    "hour":               int(row["hour"])    if pd.notna(row["hour"])    else None,
                    "weekday":            int(row["weekday"]) if pd.notna(row["weekday"]) else None,
                    "month":              int(row["month"])   if pd.notna(row["month"])   else None,
                    "is_weekend":         bool(row["is_weekend"]) if pd.notna(row["is_weekend"]) else None,
                    "updated_at":         row["updated_at"],
                })
                rows_loaded += 1

        logger.info(f"hourly_station_statistics: {rows_loaded} rows upserted.")
    except Exception as e:
        logger.error(f"Failed to load hourly_station_statistics: {e}")

    return rows_loaded


def load_line_statistics(df: pd.DataFrame) -> int:
    """
    Upsert into line_statistics.
    Natural key: (date, line_id)
    Returns number of rows upserted.
    """
    if df.empty:
        logger.info("line_statistics: nothing to load.")
        return 0

    engine = get_engine()
    rows_loaded = 0

    try:
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(text("""
                    INSERT INTO line_statistics
                        (date, line_id, total_passengers,
                         avg_occupancy_rate, peak_hour, updated_at)
                    VALUES
                        (:date, :line_id, :total_passengers,
                         :avg_occupancy_rate, :peak_hour, :updated_at)
                    ON CONFLICT (date, line_id)
                    DO UPDATE SET
                        total_passengers   = EXCLUDED.total_passengers,
                        avg_occupancy_rate = EXCLUDED.avg_occupancy_rate,
                        peak_hour          = EXCLUDED.peak_hour,
                        updated_at         = EXCLUDED.updated_at
                """), {
                    "date":               row["date"],
                    "line_id":            int(row["line_id"]) if pd.notna(row["line_id"]) else None,
                    "total_passengers":   int(row["total_passengers"]),
                    "avg_occupancy_rate": float(row["avg_occupancy_rate"]) if pd.notna(row["avg_occupancy_rate"]) else None,
                    "peak_hour":          int(row["peak_hour"]) if pd.notna(row["peak_hour"]) else None,
                    "updated_at":         row["updated_at"],
                })
                rows_loaded += 1

        logger.info(f"line_statistics: {rows_loaded} rows upserted.")
    except Exception as e:
        logger.error(f"Failed to load line_statistics: {e}")

    return rows_loaded


def load_bus_statistics(df: pd.DataFrame) -> int:
    """
    Upsert into bus_statistics.
    Natural key: (date, bus_id)
    Returns number of rows upserted.
    """
    if df.empty:
        logger.info("bus_statistics: nothing to load.")
        return 0

    engine = get_engine()
    rows_loaded = 0

    try:
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(text("""
                    INSERT INTO bus_statistics
                        (date, bus_id, total_passengers,
                         max_occupancy_rate, avg_occupancy_rate,
                         peak_hour, updated_at)
                    VALUES
                        (:date, :bus_id, :total_passengers,
                         :max_occupancy_rate, :avg_occupancy_rate,
                         :peak_hour, :updated_at)
                    ON CONFLICT (date, bus_id)
                    DO UPDATE SET
                        total_passengers   = EXCLUDED.total_passengers,
                        max_occupancy_rate = EXCLUDED.max_occupancy_rate,
                        avg_occupancy_rate = EXCLUDED.avg_occupancy_rate,
                        peak_hour          = EXCLUDED.peak_hour,
                        updated_at         = EXCLUDED.updated_at
                """), {
                    "date":               row["date"],
                    "bus_id":             int(row["bus_id"]) if pd.notna(row["bus_id"]) else None,
                    "total_passengers":   int(row["total_passengers"]),
                    "max_occupancy_rate": float(row["max_occupancy_rate"]) if pd.notna(row["max_occupancy_rate"]) else None,
                    "avg_occupancy_rate": float(row["avg_occupancy_rate"]) if pd.notna(row["avg_occupancy_rate"]) else None,
                    "peak_hour":          int(row["peak_hour"]) if pd.notna(row["peak_hour"]) else None,
                    "updated_at":         row["updated_at"],
                })
                rows_loaded += 1

        logger.info(f"bus_statistics: {rows_loaded} rows upserted.")
    except Exception as e:
        logger.error(f"Failed to load bus_statistics: {e}")

    return rows_loaded


# ---------------------------------------------------------------------------
# Watermark update
# ---------------------------------------------------------------------------

def load_daily_system(df: pd.DataFrame) -> int:
    """
    Upsert into daily_system_statistics.
    Natural key: date (unique)
    Returns number of rows upserted.
    """
    if df.empty:
        logger.info("daily_system_statistics: nothing to load.")
        return 0

    engine = get_engine()
    rows_loaded = 0

    try:
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(text("""
                    INSERT INTO daily_system_statistics
                        (date, total_passengers, avg_occupancy_rate,
                         peak_hour, busiest_line_id, updated_at)
                    VALUES
                        (:date, :total_passengers, :avg_occupancy_rate,
                         :peak_hour, :busiest_line_id, :updated_at)
                    ON CONFLICT (date)
                    DO UPDATE SET
                        total_passengers   = EXCLUDED.total_passengers,
                        avg_occupancy_rate = EXCLUDED.avg_occupancy_rate,
                        peak_hour          = EXCLUDED.peak_hour,
                        busiest_line_id    = EXCLUDED.busiest_line_id,
                        updated_at         = EXCLUDED.updated_at
                """), {
                    "date":               row["date"],
                    "total_passengers":   int(row["total_passengers"]),
                    "avg_occupancy_rate": float(row["avg_occupancy_rate"]) if pd.notna(row["avg_occupancy_rate"]) else None,
                    "peak_hour":          int(row["peak_hour"]) if pd.notna(row["peak_hour"]) else None,
                    "busiest_line_id":    int(row["busiest_line_id"]) if pd.notna(row.get("busiest_line_id")) else None,
                    "updated_at":         row["updated_at"],
                })
                rows_loaded += 1

        logger.info(f"daily_system_statistics: {rows_loaded} rows upserted.")
    except Exception as e:
        logger.error(f"Failed to load daily_system_statistics: {e}")

    return rows_loaded


def load_station_daily(df: pd.DataFrame) -> int:
    """
    Upsert into station_daily_statistics.
    Natural key: (date, station_id, COALESCE(line_id, -1))
    Skips rows where station_id is NULL.
    Returns number of rows upserted.
    """
    if df.empty:
        logger.info("station_daily_statistics: nothing to load.")
        return 0

    # Drop rows with no station_id — they carry no useful BI value
    df = df[df["station_id"].notna()].copy()
    if df.empty:
        logger.info("station_daily_statistics: no rows with valid station_id.")
        return 0

    engine = get_engine()
    rows_loaded = 0

    try:
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(text("""
                    INSERT INTO station_daily_statistics
                        (date, station_id, line_id,
                         total_boardings, total_alightings,
                         avg_occupancy_rate, peak_hour, updated_at)
                    VALUES
                        (:date, :station_id, :line_id,
                         :total_boardings, :total_alightings,
                         :avg_occupancy_rate, :peak_hour, :updated_at)
                    ON CONFLICT (date, station_id, COALESCE(line_id, -1))
                    DO UPDATE SET
                        total_boardings    = EXCLUDED.total_boardings,
                        total_alightings   = EXCLUDED.total_alightings,
                        avg_occupancy_rate = EXCLUDED.avg_occupancy_rate,
                        peak_hour          = EXCLUDED.peak_hour,
                        updated_at         = EXCLUDED.updated_at
                """), {
                    "date":               row["date"],
                    "station_id":         int(row["station_id"]),
                    "line_id":            int(row["line_id"]) if pd.notna(row["line_id"]) else None,
                    "total_boardings":    int(row["total_boardings"]),
                    "total_alightings":   int(row["total_alightings"]),
                    "avg_occupancy_rate": float(row["avg_occupancy_rate"]) if pd.notna(row["avg_occupancy_rate"]) else None,
                    "peak_hour":          int(row["peak_hour"]) if pd.notna(row["peak_hour"]) else None,
                    "updated_at":         row["updated_at"],
                })
                rows_loaded += 1

        logger.info(f"station_daily_statistics: {rows_loaded} rows upserted.")
    except Exception as e:
        logger.error(f"Failed to load station_daily_statistics: {e}")

    return rows_loaded


def load_ticket_stats(df: pd.DataFrame) -> int:
    """
    Upsert into ticket_stats.
    Natural key: (date, line_id, station_id)
    Returns number of rows upserted.
    """
    if df.empty:
        logger.info("ticket_stats: nothing to load.")
        return 0

    engine = get_engine()
    rows_loaded = 0

    try:
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(text("""
                    INSERT INTO ticket_stats
                        (date, line_id, station_id,
                         total_tickets_sold, updated_at)
                    VALUES
                        (:date, :line_id, :station_id,
                         :total_tickets_sold, :updated_at)
                    ON CONFLICT (date, line_id, station_id)
                    DO UPDATE SET
                        total_tickets_sold = EXCLUDED.total_tickets_sold,
                        updated_at         = EXCLUDED.updated_at
                """), {
                    "date":               row["date"],
                    "line_id":            int(row["line_id"])    if pd.notna(row["line_id"])    else None,
                    "station_id":         int(row["station_id"]) if pd.notna(row["station_id"]) else None,
                    "total_tickets_sold": int(row["total_tickets_sold"]),
                    "updated_at":         row["updated_at"],
                })
                rows_loaded += 1

        logger.info(f"ticket_stats: {rows_loaded} rows upserted.")
    except Exception as e:
        logger.error(f"Failed to load ticket_stats: {e}")

    return rows_loaded


def update_watermark(pipeline_name: str = "main") -> None:
    engine = get_engine()
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO etl_watermark (pipeline_name, last_run_at)
                VALUES (:name, :ts)
                ON CONFLICT (pipeline_name)
                DO UPDATE SET last_run_at = EXCLUDED.last_run_at
            """), {"name": pipeline_name, "ts": now})
        logger.info(f"Watermark updated to {now.isoformat()}")
    except Exception as e:
        logger.error(f"Failed to update watermark: {e}")


# ---------------------------------------------------------------------------
# Main load entry point
# ---------------------------------------------------------------------------

def load_all(transformed: dict, pipeline_name: str = "main") -> dict:
    """
    Load all three analytics tables and update the watermark.

    Args:
        transformed: output of transform.transform_all()
        pipeline_name: name used for the ETL watermark

    Returns:
        dict of row counts per table
    """
    if transformed.get("quality_halt"):
        logger.error("Quality halt triggered — load step aborted.")
        return {
            "hourly_station": 0,
            "line_stats":     0,
            "bus_stats":      0,
            "station_daily":  0,
            "daily_system":   0,
            "ticket_stats":   0,
        }

    counts = {
        "hourly_station": load_hourly_station(transformed["hourly_station"]),
        "line_stats":     load_line_statistics(transformed["line_stats"]),
        "bus_stats":      load_bus_statistics(transformed["bus_stats"]),
        "station_daily":  load_station_daily(transformed.get("station_daily", pd.DataFrame())),
        "daily_system":   load_daily_system(transformed["daily_system"]),
        "ticket_stats":   load_ticket_stats(transformed.get("ticket_stats", pd.DataFrame())),
    }

    update_watermark(pipeline_name)
    return counts
