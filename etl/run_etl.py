import sys
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup — file + console
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

log_filename = LOG_DIR / f"etl_{datetime.now().strftime('%Y-%m-%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)

logger = logging.getLogger("etl.runner")

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run(pipeline_name: str = "main") -> int:
    """
    Execute the full ETL pipeline.
    Returns 0 on success, 1 on failure.
    """
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 55)
    logger.info("  SmartTransport ETL Pipeline — START")
    logger.info(f"  Run at: {start_time.isoformat()}")
    logger.info("=" * 55)

    # ── Extract ──────────────────────────────────────────────
    logger.info("── Step 1: Extract")
    try:
        from etl.extract import extract_all
    except ModuleNotFoundError:
        from extract import extract_all   # fallback when run as __main__
    try:
        extracted = extract_all(pipeline_name)
        event_count = len(extracted["events"])
        logger.info(f"   Events extracted : {event_count}")
        logger.info(f"   Buses loaded     : {len(extracted['buses'])}")
        logger.info(f"   Lines loaded     : {len(extracted['lines'])}")
        logger.info(f"   Tickets extracted: {len(extracted.get('tickets', []))}")
    except Exception as e:
        logger.error(f"Extract step failed: {e}")
        return 1

    if event_count == 0:
        logger.info("No new events since last run. Pipeline complete.")
        _log_summary(start_time, {"hourly_station": 0, "line_stats": 0, "bus_stats": 0})
        return 0

    # ── Transform ────────────────────────────────────────────
    logger.info("── Step 2: Transform")
    try:
        from etl.transform import transform_all
    except ModuleNotFoundError:
        from transform import transform_all
    try:
        transformed = transform_all(extracted)
        logger.info(f"   hourly_station rows : {len(transformed['hourly_station'])}")
        logger.info(f"   line_stats rows     : {len(transformed['line_stats'])}")
        logger.info(f"   bus_stats rows      : {len(transformed['bus_stats'])}")
        logger.info(f"   station_daily rows  : {len(transformed.get('station_daily', []))}")
        logger.info(f"   daily_system rows   : {len(transformed['daily_system'])}")
        logger.info(f"   ticket_stats rows   : {len(transformed.get('ticket_stats', []))}")
    except Exception as e:
        logger.error(f"Transform step failed: {e}")
        return 1

    if transformed.get("quality_halt"):
        logger.error("Quality halt: more than 10% invalid rows. Load aborted.")
        return 1

    # ── Load ─────────────────────────────────────────────────
    logger.info("── Step 3: Load")
    try:
        from etl.load import load_all
    except ModuleNotFoundError:
        from load import load_all
    try:
        counts = load_all(transformed, pipeline_name)
        logger.info(f"   hourly_station upserted : {counts['hourly_station']}")
        logger.info(f"   line_stats upserted     : {counts['line_stats']}")
        logger.info(f"   bus_stats upserted      : {counts['bus_stats']}")
        logger.info(f"   station_daily upserted  : {counts.get('station_daily', 0)}")
        logger.info(f"   daily_system upserted   : {counts['daily_system']}")
        logger.info(f"   ticket_stats upserted   : {counts.get('ticket_stats', 0)}")
    except Exception as e:
        logger.error(f"Load step failed: {e}")
        return 1

    _log_summary(start_time, counts)
    return 0


def _log_summary(start_time: datetime, counts: dict) -> None:
    end_time  = datetime.now(timezone.utc)
    elapsed   = (end_time - start_time).total_seconds()
    total_rows = sum(counts.values())

    logger.info("=" * 55)
    logger.info("  ETL Pipeline — COMPLETE")
    logger.info(f"  Duration  : {elapsed:.1f}s")
    logger.info(f"  Rows loaded: {total_rows}")
    logger.info("=" * 55)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run())
