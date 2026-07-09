"""
etl/transform.py
----------------
Applies business logic to raw extracted data and produces
aggregated DataFrames ready to load into analytics tables.

Responsibilities:
  - Validate and clean raw events
  - Enrich events with line_id from buses master data
  - Aggregate into three analytics shapes:
      1. hourly_station_statistics  (per station per hour)
      2. line_statistics             (per line per day)
      3. bus_statistics              (per bus per day)

Nothing is read from or written to the database here.
Input and output are pure DataFrames.
"""

import logging
import pandas as pd
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation / cleaning
# ---------------------------------------------------------------------------

def clean_events(events: pd.DataFrame) -> pd.DataFrame:
    """
    Remove invalid rows and log how many were dropped.

    Invalid rows:
      - occupancy_after_event < 0
      - direction not in ('IN', 'OUT')
      - timestamp is null
    """
    original = len(events)

    if original == 0:
        return events

    mask = (
        (events["occupancy_after_event"] >= 0) &
        (events["direction"].isin(["IN", "OUT"])) &
        (events["timestamp"].notna())
    )

    clean = events[mask].copy()
    dropped = original - len(clean)

    if dropped > 0:
        pct = dropped / original * 100
        logger.warning(f"Dropped {dropped} invalid rows ({pct:.1f}%).")
        if pct > 10:
            logger.error(
                f"More than 10% of rows are invalid ({pct:.1f}%). "
                "Load step will be halted for safety."
            )
            clean.attrs["quality_halt"] = True
        else:
            clean.attrs["quality_halt"] = False
    else:
        clean.attrs["quality_halt"] = False

    logger.info(f"Clean events: {len(clean)} rows.")
    return clean


# ---------------------------------------------------------------------------
# Enrichment — join line_id from buses master data
# ---------------------------------------------------------------------------

def enrich_with_line(events: pd.DataFrame, buses: pd.DataFrame) -> pd.DataFrame:
    """
    Add line_id to every event row via bus → line mapping.
    Events with no matching bus will have line_id = NaN.
    """
    if events.empty or buses.empty:
        events["line_id"] = None
        return events

    bus_line = buses[["bus_id", "line_id"]].drop_duplicates()
    enriched = events.merge(bus_line, on="bus_id", how="left")
    logger.info("Events enriched with line_id.")
    return enriched


# ---------------------------------------------------------------------------
# Transform 1 — hourly_station_statistics
# ---------------------------------------------------------------------------

def transform_hourly_station(events: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate events by (station_id, line_id, hour).

    Output columns:
        hour_start, station_id, line_id,
        total_boardings, total_alightings, avg_occupancy_rate,
        hour, weekday, month, is_weekend
    """
    if events.empty:
        logger.info("No events to aggregate for hourly_station_statistics.")
        return pd.DataFrame()

    df = events.copy()
    df["hour_start"] = df["timestamp"].dt.floor("h")

    df["is_in"]  = (df["direction"] == "IN").astype(int)
    df["is_out"] = (df["direction"] == "OUT").astype(int)

    group_cols = ["hour_start", "station_id", "line_id"]

    agg = df.groupby(group_cols, dropna=False).agg(
        total_boardings    =("is_in",          "sum"),
        total_alightings   =("is_out",         "sum"),
        avg_occupancy_rate =("occupancy_rate",  "mean"),
    ).reset_index()

    # Temporal features derived from hour_start
    # weekday: 0=Monday … 6=Sunday (ISO convention)
    agg["hour"]       = agg["hour_start"].dt.hour.astype("Int64")
    agg["weekday"]    = agg["hour_start"].dt.weekday.astype("Int64")  # 0=Mon, 6=Sun
    agg["month"]      = agg["hour_start"].dt.month.astype("Int64")
    agg["is_weekend"] = agg["weekday"] >= 5                           # Sat=5, Sun=6

    agg["avg_occupancy_rate"] = agg["avg_occupancy_rate"].round(2)
    agg["updated_at"] = datetime.now(timezone.utc)

    logger.info(f"hourly_station_statistics: {len(agg)} rows.")
    return agg


# ---------------------------------------------------------------------------
# Transform 2 — line_statistics
# ---------------------------------------------------------------------------

def transform_line_statistics(events: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate events by (line_id, date).

    Output columns:
        date, line_id,
        total_passengers, avg_occupancy_rate, peak_hour
    """
    if events.empty or "line_id" not in events.columns:
        logger.info("No events to aggregate for line_statistics.")
        return pd.DataFrame()

    df = events.copy()
    df["date"]  = df["timestamp"].dt.date
    df["hour"]  = df["timestamp"].dt.hour
    df["is_in"] = (df["direction"] == "IN").astype(int)

    # Daily totals per line
    daily = df.groupby(["date", "line_id"], dropna=True).agg(
        total_passengers   =("is_in",          "sum"),
        avg_occupancy_rate =("occupancy_rate",  "mean"),
    ).reset_index()

    # Peak hour = hour with highest mean occupancy_rate per (date, line_id)
    hourly_occ = df.groupby(["date", "line_id", "hour"], dropna=True).agg(
        mean_occ=("occupancy_rate", "mean")
    ).reset_index()

    peak = (
        hourly_occ
        .sort_values("mean_occ", ascending=False)
        .drop_duplicates(subset=["date", "line_id"])
        [["date", "line_id", "hour"]]
        .rename(columns={"hour": "peak_hour"})
    )

    result = daily.merge(peak, on=["date", "line_id"], how="left")
    result["avg_occupancy_rate"] = result["avg_occupancy_rate"].round(2)
    result["peak_hour"] = result["peak_hour"].astype("Int64")  # nullable int
    result["updated_at"] = datetime.now(timezone.utc)

    logger.info(f"line_statistics: {len(result)} rows.")
    return result


# ---------------------------------------------------------------------------
# Transform 3 — bus_statistics
# ---------------------------------------------------------------------------

def transform_bus_statistics(events: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate events by (bus_id, date).

    Output columns:
        date, bus_id,
        total_passengers, max_occupancy_rate, avg_occupancy_rate, peak_hour
    """
    if events.empty:
        logger.info("No events to aggregate for bus_statistics.")
        return pd.DataFrame()

    df = events.copy()
    df["date"]  = df["timestamp"].dt.date
    df["hour"]  = df["timestamp"].dt.hour
    df["is_in"] = (df["direction"] == "IN").astype(int)

    # Daily totals per bus
    daily = df.groupby(["date", "bus_id"], dropna=True).agg(
        total_passengers   =("is_in",          "sum"),
        avg_occupancy_rate =("occupancy_rate",  "mean"),
        max_occupancy_rate =("occupancy_rate",  "max"),
    ).reset_index()

    # Peak hour per (date, bus_id)
    hourly_occ = df.groupby(["date", "bus_id", "hour"], dropna=True).agg(
        mean_occ=("occupancy_rate", "mean")
    ).reset_index()

    peak = (
        hourly_occ
        .sort_values("mean_occ", ascending=False)
        .drop_duplicates(subset=["date", "bus_id"])
        [["date", "bus_id", "hour"]]
        .rename(columns={"hour": "peak_hour"})
    )

    result = daily.merge(peak, on=["date", "bus_id"], how="left")
    result["avg_occupancy_rate"] = result["avg_occupancy_rate"].round(2)
    result["max_occupancy_rate"] = result["max_occupancy_rate"].round(2)
    result["peak_hour"] = result["peak_hour"].astype("Int64")
    result["updated_at"] = datetime.now(timezone.utc)

    logger.info(f"bus_statistics: {len(result)} rows.")
    return result


# ---------------------------------------------------------------------------
# Transform 4 — daily_system_statistics
# ---------------------------------------------------------------------------

def transform_station_daily(events: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate events by (date, station_id, line_id).

    Consistent dimensional design: date / station_id / line_id

    Output columns:
        date, station_id, line_id,
        total_boardings, total_alightings, avg_occupancy_rate, peak_hour
    """
    if events.empty or "station_id" not in events.columns:
        logger.info("No events to aggregate for station_daily_statistics.")
        return pd.DataFrame()

    df = events.copy()
    df["date"]  = df["timestamp"].dt.date
    df["hour"]  = df["timestamp"].dt.hour
    df["is_in"] = (df["direction"] == "IN").astype(int)
    df["is_out"] = (df["direction"] == "OUT").astype(int)

    group_cols = ["date", "station_id", "line_id"]

    daily = df.groupby(group_cols, dropna=False).agg(
        total_boardings    =("is_in",          "sum"),
        total_alightings   =("is_out",         "sum"),
        avg_occupancy_rate =("occupancy_rate",  "mean"),
    ).reset_index()

    # Peak hour per (date, station_id, line_id)
    hourly_occ = df.groupby(
        ["date", "station_id", "line_id", "hour"], dropna=False
    ).agg(mean_occ=("occupancy_rate", "mean")).reset_index()

    peak = (
        hourly_occ
        .sort_values("mean_occ", ascending=False)
        .drop_duplicates(subset=["date", "station_id", "line_id"])
        [["date", "station_id", "line_id", "hour"]]
        .rename(columns={"hour": "peak_hour"})
    )

    result = daily.merge(peak, on=group_cols, how="left")
    result["avg_occupancy_rate"] = result["avg_occupancy_rate"].round(2)
    result["peak_hour"]          = result["peak_hour"].astype("Int64")
    result["updated_at"]         = datetime.now(timezone.utc)

    logger.info(f"station_daily_statistics: {len(result)} rows.")
    return result


def transform_daily_system(events: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate all events across the entire network by date.

    Output columns:
        date, total_passengers, avg_occupancy_rate, peak_hour, busiest_line_id
    """
    if events.empty:
        logger.info("No events to aggregate for daily_system_statistics.")
        return pd.DataFrame()

    df = events.copy()
    df["date"]  = df["timestamp"].dt.date
    df["hour"]  = df["timestamp"].dt.hour
    df["is_in"] = (df["direction"] == "IN").astype(int)

    # Daily network totals
    daily = df.groupby("date", dropna=True).agg(
        total_passengers   =("is_in",          "sum"),
        avg_occupancy_rate =("occupancy_rate",  "mean"),
    ).reset_index()

    # Peak hour = hour with highest mean occupancy across the whole network
    hourly_occ = df.groupby(["date", "hour"], dropna=True).agg(
        mean_occ=("occupancy_rate", "mean")
    ).reset_index()

    peak = (
        hourly_occ
        .sort_values("mean_occ", ascending=False)
        .drop_duplicates(subset=["date"])
        [["date", "hour"]]
        .rename(columns={"hour": "peak_hour"})
    )

    # Busiest line = line with most boardings that day
    if "line_id" in df.columns:
        line_boardings = (
            df[df["direction"] == "IN"]
            .groupby(["date", "line_id"], dropna=True)
            .agg(boardings=("is_in", "sum"))
            .reset_index()
            .sort_values("boardings", ascending=False)
            .drop_duplicates(subset=["date"])
            [["date", "line_id"]]
            .rename(columns={"line_id": "busiest_line_id"})
        )
    else:
        line_boardings = pd.DataFrame(columns=["date", "busiest_line_id"])

    result = daily.merge(peak, on="date", how="left")
    result = result.merge(line_boardings, on="date", how="left")

    result["avg_occupancy_rate"] = result["avg_occupancy_rate"].round(2)
    result["peak_hour"]          = result["peak_hour"].astype("Int64")
    result["updated_at"]         = datetime.now(timezone.utc)

    logger.info(f"daily_system_statistics: {len(result)} rows.")
    return result


# ---------------------------------------------------------------------------
# Transform 5 — ticket_stats
# ---------------------------------------------------------------------------

def transform_ticket_stats(tickets: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate ticket_sales by (date, line_id, station_id).

    ticket_sales is manually entered — no cleaning needed beyond
    ensuring timestamp is valid. NULL line_id or station_id rows
    are kept (partial aggregations are still useful).

    Output columns:
        date, line_id, station_id, total_tickets_sold, updated_at
    """
    if tickets.empty:
        logger.info("No ticket_sales rows to aggregate.")
        return pd.DataFrame()

    df = tickets.copy()

    # Ensure timestamp is tz-aware
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    elif df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")

    df["date"] = df["timestamp"].dt.date

    group_cols = ["date", "line_id", "station_id"]

    result = df.groupby(group_cols, dropna=False).agg(
        total_tickets_sold=("tickets_sold", "sum"),
    ).reset_index()

    result["updated_at"] = datetime.now(timezone.utc)

    logger.info(f"ticket_stats: {len(result)} rows.")
    return result


# ---------------------------------------------------------------------------
# Main transform entry point
# ---------------------------------------------------------------------------

def transform_all(extracted: dict) -> dict:
    """
    Run the full transform step.

    Args:
        extracted: output of extract.extract_all()

    Returns:
        {
            "hourly_station": DataFrame,
            "line_stats":     DataFrame,
            "bus_stats":      DataFrame,
            "quality_halt":   bool
        }
    """
    events  = extracted["events"]
    buses   = extracted["buses"]
    tickets = extracted.get("tickets", pd.DataFrame())

    if events.empty:
        logger.info("No new events to transform.")
        # Still process tickets even if no new CV events
        ticket_stats = transform_ticket_stats(tickets)
        return {
            "hourly_station": pd.DataFrame(),
            "line_stats":     pd.DataFrame(),
            "bus_stats":      pd.DataFrame(),
            "daily_system":   pd.DataFrame(),
            "ticket_stats":   ticket_stats,
            "quality_halt":   False,
        }

    # Ensure timestamp is timezone-aware
    if not pd.api.types.is_datetime64_any_dtype(events["timestamp"]):
        events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True)
    elif events["timestamp"].dt.tz is None:
        events["timestamp"] = events["timestamp"].dt.tz_localize("UTC")

    # 1. Clean
    events = clean_events(events)
    quality_halt = events.attrs.get("quality_halt", False)

    # 2. Enrich
    events = enrich_with_line(events, buses)

    # 3. Aggregate
    hourly_station = transform_hourly_station(events)
    line_stats     = transform_line_statistics(events)
    bus_stats      = transform_bus_statistics(events)
    station_daily  = transform_station_daily(events)
    daily_system   = transform_daily_system(events)
    ticket_stats   = transform_ticket_stats(tickets)

    return {
        "hourly_station": hourly_station,
        "line_stats":     line_stats,
        "bus_stats":      bus_stats,
        "station_daily":  station_daily,
        "daily_system":   daily_system,
        "ticket_stats":   ticket_stats,
        "quality_halt":   quality_halt,
    }
