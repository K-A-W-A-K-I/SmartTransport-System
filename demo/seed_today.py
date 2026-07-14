"""
demo/seed_today.py
-------------------
Injects realistic "today" data into PostgreSQL so every portal KPI
shows live numbers instead of zeros.

What it creates (all timestamped to today):
  - 4 sessions  (one per bus, spread across morning rush hours)
  - ~300 passenger events  (entries + exits with realistic occupancy)
  - ~80 ticket sales
  - 6 recommendations  (mix of CRITICAL / HIGH / MEDIUM)

Safe to run multiple times — it checks for existing today data first
and skips if already seeded.

Usage:
    python -m demo.seed_today
    python demo/seed_today.py
"""

import sys
import random
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.config import init_engine
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("seed_today")

random.seed()   # different each run for variety

TODAY = date.today()
NOW   = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ts(hour: int, minute: int = 0, second: int = 0) -> datetime:
    """Return a timezone-aware datetime for today at the given time."""
    return datetime(TODAY.year, TODAY.month, TODAY.day,
                    hour, minute, second, tzinfo=timezone.utc)


def rand_minute() -> int:
    return random.randint(0, 59)


def rand_second() -> int:
    return random.randint(0, 59)


# ---------------------------------------------------------------------------
# Guard — skip if today is already seeded
# ---------------------------------------------------------------------------

def already_seeded(conn) -> bool:
    n = conn.execute(text("""
        SELECT COUNT(*) FROM sessions
        WHERE session_start::date = :today
    """), {"today": TODAY}).scalar()
    return int(n) > 0


# ---------------------------------------------------------------------------
# Load existing master data
# ---------------------------------------------------------------------------

def load_master(conn) -> dict:
    buses = conn.execute(text(
        "SELECT bus_id, capacity, line_id FROM buses ORDER BY bus_id LIMIT 4"
    )).fetchall()

    lines = {r[0]: r[1] for r in conn.execute(text(
        "SELECT line_id, line_number FROM lines"
    )).fetchall()}

    stations = conn.execute(text(
        "SELECT station_id FROM line_stations ORDER BY line_id, stop_order"
    )).fetchall()
    station_ids = [r[0] for r in stations]

    return {
        "buses":       [dict(b._mapping) for b in buses],
        "lines":       lines,
        "station_ids": station_ids,
    }


# ---------------------------------------------------------------------------
# Sessions + passenger events
# ---------------------------------------------------------------------------

def seed_sessions(conn, master: dict) -> list[dict]:
    """
    Create 4 sessions (morning + midday rush) and a stream of
    passenger events for each. Returns session metadata.
    """
    buses = master["buses"]
    station_ids = master["station_ids"]

    # One session per bus, staggered start times
    session_configs = [
        {"start_h": 7, "start_m": 0,  "duration_min": 90,  "base_pax": 40},
        {"start_h": 8, "start_m": 15, "duration_min": 75,  "base_pax": 35},
        {"start_h": 9, "start_m": 30, "duration_min": 60,  "base_pax": 25},
        {"start_h": 12, "start_m": 0, "duration_min": 45,  "base_pax": 20},
    ]

    sessions_created = []

    for i, (bus, cfg) in enumerate(zip(buses, session_configs)):
        bus_id    = bus["bus_id"]
        capacity  = bus["capacity"]
        line_id   = bus.get("line_id")
        start     = ts(cfg["start_h"], cfg["start_m"])
        end       = start + timedelta(minutes=cfg["duration_min"])
        station_id = station_ids[i % len(station_ids)]

        # Insert session
        row = conn.execute(text("""
            INSERT INTO sessions
                (bus_id, session_start, session_end, mode, video_file,
                 entry_count, exit_count)
            VALUES
                (:bus_id, :start, :end, 'color', 'today_demo.mp4', 0, 0)
            RETURNING id
        """), {"bus_id": bus_id, "start": start, "end": end}).fetchone()
        session_id = row[0]

        # Generate passenger events
        entry_count = 0
        exit_count  = 0
        occupancy   = random.randint(5, 15)   # start with some passengers
        total_events = cfg["base_pax"] + random.randint(-5, 15)

        for _ in range(total_events):
            # Weighted: more entries during rush, exits spread out
            direction = "IN" if random.random() < 0.62 else "OUT"
            offset_s  = random.randint(0, cfg["duration_min"] * 60)
            event_ts  = start + timedelta(seconds=offset_s)

            if direction == "IN":
                occupancy   = min(occupancy + 1, capacity)
                entry_count += 1
            else:
                occupancy   = max(occupancy - 1, 0)
                exit_count  += 1

            occ_rate = round(occupancy / capacity * 100, 2) if capacity else None

            conn.execute(text("""
                INSERT INTO passenger_events
                    (session_id, bus_id, station_id, timestamp,
                     direction, occupancy_after_event, occupancy_rate)
                VALUES
                    (:session_id, :bus_id, :station_id, :ts,
                     :direction, :occupancy, :occ_rate)
            """), {
                "session_id": session_id,
                "bus_id":     bus_id,
                "station_id": station_id,
                "ts":         event_ts,
                "direction":  direction,
                "occupancy":  occupancy,
                "occ_rate":   occ_rate,
            })

        # Update session totals
        conn.execute(text("""
            UPDATE sessions
            SET entry_count = :e, exit_count = :x
            WHERE id = :sid
        """), {"e": entry_count, "x": exit_count, "sid": session_id})

        sessions_created.append({
            "session_id":   session_id,
            "bus_id":       bus_id,
            "line_id":      line_id,
            "station_id":   station_id,
            "entry_count":  entry_count,
            "exit_count":   exit_count,
        })
        logger.info(f"  Session {session_id}: bus {bus_id} | "
                    f"IN={entry_count} OUT={exit_count}")

    return sessions_created


# ---------------------------------------------------------------------------
# Ticket sales
# ---------------------------------------------------------------------------

def seed_tickets(conn, master: dict) -> int:
    """Insert ticket sales spread across today's hours."""
    station_ids = master["station_ids"]
    buses       = master["buses"]
    count       = 0

    # Spread tickets across 6am–3pm
    for hour in range(6, 15):
        n_sales = random.randint(3, 10)
        for _ in range(n_sales):
            bus    = random.choice(buses)
            st_id  = random.choice(station_ids)
            minute = rand_minute()
            second = rand_second()

            conn.execute(text("""
                INSERT INTO ticket_sales
                    (bus_id, line_id, station_id, timestamp,
                     tickets_sold, entered_by)
                VALUES
                    (:bus_id, :line_id, :station_id, :ts,
                     :tickets, 'seed_today')
            """), {
                "bus_id":    bus["bus_id"],
                "line_id":   bus.get("line_id"),
                "station_id": st_id,
                "ts":        ts(hour, minute, second),
                "tickets":   random.randint(1, 8),
            })
            count += 1

    logger.info(f"  Ticket sales inserted: {count}")
    return count


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def seed_recommendations(conn, master: dict) -> int:
    """Insert a mix of today's AI recommendations."""
    buses  = master["buses"]
    count  = 0

    recs = [
        {
            "severity": "CRITICAL",
            "hour": 8,
            "pred_occ": 97.3,
            "pred_pax": 48,
            "action": "Deploy additional bus immediately",
            "message": "Deploy one additional bus — predicted occupancy 97% at 08:00.",
            "status": "pending",
        },
        {
            "severity": "HIGH",
            "hour": 9,
            "pred_occ": 84.1,
            "pred_pax": 42,
            "action": "Pre-position standby bus",
            "message": "Pre-position a standby bus before 09:00.",
            "status": "pending",
        },
        {
            "severity": "HIGH",
            "hour": 7,
            "pred_occ": 81.5,
            "pred_pax": 40,
            "action": "Adjust permanent schedule",
            "message": "This slot has been over 80% for 4 of the last 7 days.",
            "status": "acknowledged",
        },
        {
            "severity": "MEDIUM",
            "hour": 12,
            "pred_occ": 68.2,
            "pred_pax": 34,
            "action": "Monitor and alert driver",
            "message": "Alert driver to expect higher load at 12:00.",
            "status": "pending",
        },
        {
            "severity": "MEDIUM",
            "hour": 17,
            "pred_occ": 72.0,
            "pred_pax": 36,
            "action": "Monitor and alert driver",
            "message": "Evening rush expected — alert drivers on Line 23.",
            "status": "pending",
        },
        {
            "severity": "LOW",
            "hour": 14,
            "pred_occ": 18.5,
            "pred_pax": 9,
            "action": "Consider reducing frequency",
            "message": "14:00 slot at only 18% capacity — consider smaller vehicle.",
            "status": "resolved",
        },
    ]

    for i, rec in enumerate(recs):
        bus       = buses[i % len(buses)]
        line_id   = bus.get("line_id")
        st_id     = master["station_ids"][i % len(master["station_ids"])]
        created   = ts(rec["hour"] - 1, rand_minute())

        ack_at = None
        res_at = None
        if rec["status"] == "acknowledged":
            ack_at = ts(rec["hour"], rand_minute())
        elif rec["status"] == "resolved":
            ack_at = ts(rec["hour"], 10)
            res_at = ts(rec["hour"], 30)

        conn.execute(text("""
            INSERT INTO recommendations
                (created_at, prediction_date, line_id, station_id, hour,
                 predicted_occupancy, predicted_passengers,
                 severity, action, recommendation, status,
                 acknowledged_at, resolved_at)
            VALUES
                (:created_at, :pred_date, :line_id, :station_id, :hour,
                 :pred_occ, :pred_pax,
                 :severity, :action, :message, :status,
                 :ack_at, :res_at)
        """), {
            "created_at": created,
            "pred_date":  TODAY,
            "line_id":    line_id,
            "station_id": st_id,
            "hour":       rec["hour"],
            "pred_occ":   rec["pred_occ"],
            "pred_pax":   rec["pred_pax"],
            "severity":   rec["severity"],
            "action":     rec["action"],
            "message":    rec["message"],
            "status":     rec["status"],
            "ack_at":     ack_at,
            "res_at":     res_at,
        })
        count += 1

    logger.info(f"  Recommendations inserted: {count}")
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    logger.info("=" * 50)
    logger.info(f"  Seeding today's data — {TODAY}")
    logger.info("=" * 50)

    engine = init_engine()

    with engine.begin() as conn:
        if already_seeded(conn):
            logger.info("Today's data already exists. Nothing to do.")
            logger.info("To re-seed, delete today's sessions first:")
            logger.info("  DELETE FROM sessions WHERE session_start::date = CURRENT_DATE;")
            return

        logger.info("Loading master data...")
        master = load_master(conn)
        if not master["buses"]:
            logger.error("No buses found. Run migrations and seed master data first.")
            sys.exit(1)

        logger.info(f"Found {len(master['buses'])} buses, "
                    f"{len(master['station_ids'])} stations")

        logger.info("Seeding sessions + passenger events...")
        sessions = seed_sessions(conn, master)

        logger.info("Seeding ticket sales...")
        seed_tickets(conn, master)

        logger.info("Seeding recommendations...")
        seed_recommendations(conn, master)

    logger.info("=" * 50)
    logger.info("  Done! Running ETL to populate analytics tables...")
    logger.info("=" * 50)

    # Run ETL so the dashboard KPIs reflect today's data
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "etl.run_etl"],
        cwd=str(Path(__file__).parent.parent),
    )

    if result.returncode == 0:
        logger.info("ETL complete. Open http://localhost:5000 to see live data.")
    else:
        logger.warning("ETL had issues — check etl/logs/ for details.")


if __name__ == "__main__":
    run()
