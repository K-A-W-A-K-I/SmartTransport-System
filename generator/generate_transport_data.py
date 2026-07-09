"""
generator/generate_transport_data.py
-------------------------------------
Generates 90 days of realistic synthetic transport data and inserts it
directly into PostgreSQL.

What gets generated:
  - 3 lines, 12 stations, 8 buses, 4 drivers (extends existing master data)
  - 90 days × 18 operating hours × multiple buses
  - passenger_events with realistic rush hour patterns
  - ticket_sales approximately matching passenger counts
  - sessions wrapping each bus-hour block

Rush hour model:
  07–09  →  high demand   (factor 1.8)
  09–12  →  moderate      (factor 1.0)
  12–14  →  lunch peak    (factor 1.3)
  14–16  →  quiet         (factor 0.7)
  16–19  →  evening rush  (factor 1.9)
  19–21  →  tapering      (factor 0.8)
  21–01  →  low           (factor 0.3)

Weekend modifier: 0.6× for commuter lines, 1.1× for tourist/shopping lines.

Usage:
  python -m generator.generate_transport_data
  python -m generator.generate_transport_data --days 30 --dry-run
"""

import argparse
import logging
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

# ---------------------------------------------------------------------------
# Setup path so we can import from project root
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.config import init_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("generator")

# ---------------------------------------------------------------------------
# Master data to seed (extends existing DB rows)
# ---------------------------------------------------------------------------

NEW_LINES = [
    {"line_id": 3, "line_name": "Bardo - Manouba",       "line_number": "15"},
]

NEW_STATIONS = [
    {"station_id": 30, "station_name": "Manouba Centre"},
    {"station_id": 31, "station_name": "Cité El Khadra"},
    {"station_id": 32, "station_name": "Ibn Khaldoun"},
]

NEW_DRIVERS = [
    {"driver_id": 3, "first_name": "Khaled",  "last_name": "Mansouri", "license_number": "TN-DRV-003"},
    {"driver_id": 4, "first_name": "Mohamed", "last_name": "Gharbi",   "license_number": "TN-DRV-004"},
]

NEW_BUSES = [
    {"bus_id": 3, "capacity": 50, "line_id": 1, "license_plate": "TU-103-EF", "driver_id": 3},
    {"bus_id": 4, "capacity": 45, "line_id": 1, "license_plate": "TU-104-GH", "driver_id": 4},
    {"bus_id": 5, "capacity": 35, "line_id": 2, "license_plate": "TU-105-IJ", "driver_id": 1},
    {"bus_id": 6, "capacity": 50, "line_id": 2, "license_plate": "TU-106-KL", "driver_id": 2},
    {"bus_id": 7, "capacity": 40, "line_id": 3, "license_plate": "TU-107-MN", "driver_id": 3},
    {"bus_id": 8, "capacity": 45, "line_id": 3, "license_plate": "TU-108-OP", "driver_id": 4},
]

# Which stations belong to which line (ordered stops)
LINE_STATIONS = {
    1: [17, 18, 2, 20, 5],           # Line 23: Tunis Centre→Passage→Tunis Marine→La Goulette→La Marsa
    2: [3, 6, 19, 4, 21],            # Line 42: Bab Saadoun→Bardo→Le Bardo→Ariana→Ain Zaghouan
    3: [17, 22, 6, 19, 30, 31, 32],  # Line 15: Tunis Centre→Cité Sportive→Bardo→Le Bardo→Manouba
}

# Buses per line
LINE_BUSES = {
    1: [1, 3, 4],
    2: [2, 5, 6],
    3: [7, 8],
}

# Bus capacities lookup
BUS_CAPACITY = {1: 50, 2: 35, 3: 50, 4: 45, 5: 35, 6: 50, 7: 40, 8: 45}

# Operating hours (inclusive)
OPERATING_HOURS = list(range(6, 24))  # 06:00 – 23:00 = 18 hours

# Hour → demand factor
DEMAND_PROFILE = {
    6: 0.4, 7: 1.8, 8: 1.9, 9: 1.2,
    10: 0.9, 11: 0.8, 12: 1.3, 13: 1.2,
    14: 0.7, 15: 0.8, 16: 1.6, 17: 1.9,
    18: 1.8, 19: 1.0, 20: 0.7, 21: 0.5,
    22: 0.4, 23: 0.3,
}

# Line type: commuter vs tourist/shopping (affects weekend modifier)
LINE_TYPE = {1: "commuter", 2: "commuter", 3: "commuter"}
WEEKEND_MODIFIER = {"commuter": 0.55, "tourist": 1.1}

# Base passengers per station stop per hour (before modifiers)
BASE_BOARDINGS = 12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def demand_factor(hour: int, is_weekend: bool, line_id: int) -> float:
    profile = DEMAND_PROFILE.get(hour, 0.3)
    if is_weekend:
        wmod = WEEKEND_MODIFIER[LINE_TYPE.get(line_id, "commuter")]
        profile *= wmod
    return profile


def random_boardings(base: int, factor: float, capacity: int, current_occupancy: int) -> int:
    """Return realistic boarding count respecting capacity."""
    space_available = max(0, capacity - current_occupancy)
    raw = int(base * factor * random.uniform(0.7, 1.3))
    return min(raw, space_available)


def random_alightings(current_occupancy: int, factor: float) -> int:
    """People alight proportional to how full the bus is."""
    if current_occupancy == 0:
        return 0
    rate = 0.3 + (1 - factor) * 0.3  # higher alighting when demand drops
    return min(current_occupancy, int(current_occupancy * rate * random.uniform(0.8, 1.2)))


def ticket_noise(passengers: int) -> int:
    """Tickets sold ≈ passengers, with small random delta (-5% to +2%)."""
    if passengers == 0:
        return 0
    delta = random.randint(-max(1, int(passengers * 0.05)), max(1, int(passengers * 0.02)))
    return max(0, passengers + delta)


# ---------------------------------------------------------------------------
# Seed master data
# ---------------------------------------------------------------------------

def seed_master_data(conn) -> None:
    logger.info("Seeding master data...")

    for line in NEW_LINES:
        conn.execute(text("""
            INSERT INTO lines (line_id, line_name, line_number)
            VALUES (:line_id, :line_name, :line_number)
            ON CONFLICT (line_id) DO NOTHING
        """), line)

    for st in NEW_STATIONS:
        conn.execute(text("""
            INSERT INTO stations (station_id, station_name)
            VALUES (:station_id, :station_name)
            ON CONFLICT (station_id) DO NOTHING
        """), st)

    for drv in NEW_DRIVERS:
        conn.execute(text("""
            INSERT INTO drivers (driver_id, first_name, last_name, license_number)
            VALUES (:driver_id, :first_name, :last_name, :license_number)
            ON CONFLICT (driver_id) DO NOTHING
        """), drv)

    for bus in NEW_BUSES:
        conn.execute(text("""
            INSERT INTO buses (bus_id, capacity, line_id, license_plate, driver_id)
            VALUES (:bus_id, :capacity, :line_id, :license_plate, :driver_id)
            ON CONFLICT (bus_id) DO NOTHING
        """), bus)

    # Seed line_stations bridge
    for line_id, station_ids in LINE_STATIONS.items():
        for order, station_id in enumerate(station_ids, start=1):
            conn.execute(text("""
                INSERT INTO line_stations (line_id, station_id, stop_order)
                VALUES (:line_id, :station_id, :stop_order)
                ON CONFLICT DO NOTHING
            """), {"line_id": line_id, "station_id": station_id, "stop_order": order})

    logger.info("Master data seeded.")


# ---------------------------------------------------------------------------
# Generate one day for one bus
# ---------------------------------------------------------------------------

def generate_bus_day(
    conn,
    sim_date: date,
    bus_id: int,
    line_id: int,
    dry_run: bool,
) -> tuple[int, int]:
    """
    Simulate one bus operating for 18 hours on a given day.
    Returns (total_events_inserted, total_ticket_rows_inserted).
    """
    is_weekend = sim_date.weekday() >= 5
    capacity   = BUS_CAPACITY[bus_id]
    stations   = LINE_STATIONS[line_id]
    events_inserted  = 0
    tickets_inserted = 0

    for hour in OPERATING_HOURS:
        factor = demand_factor(hour, is_weekend, line_id)

        # Session start/end for this hour block
        session_start = datetime(
            sim_date.year, sim_date.month, sim_date.day,
            hour, 0, 0, tzinfo=timezone.utc
        )
        session_end = session_start + timedelta(hours=1)

        entry_count = 0
        exit_count  = 0
        occupancy   = random.randint(0, int(capacity * 0.2))  # start with some passengers

        # Insert session row
        if not dry_run:
            result = conn.execute(text("""
                INSERT INTO sessions
                    (bus_id, session_start, session_end, mode, video_file,
                     entry_count, exit_count)
                VALUES
                    (:bus_id, :session_start, :session_end, 'color', 'synthetic.mp4',
                     0, 0)
                RETURNING id
            """), {
                "bus_id":        bus_id,
                "session_start": session_start,
                "session_end":   session_end,
            })
            session_id = result.fetchone()[0]
        else:
            session_id = 0

        # Simulate stops along the route
        for station_id in stations:
            # Alightings first
            alightings = random_alightings(occupancy, factor)
            for _ in range(alightings):
                ts = session_start + timedelta(
                    minutes=random.randint(0, 55),
                    seconds=random.randint(0, 59)
                )
                occ_after = max(0, occupancy - 1)
                occ_rate  = round((occ_after / capacity) * 100, 2)

                if not dry_run:
                    conn.execute(text("""
                        INSERT INTO passenger_events
                            (session_id, bus_id, station_id, timestamp,
                             direction, occupancy_after_event, occupancy_rate)
                        VALUES
                            (:session_id, :bus_id, :station_id, :timestamp,
                             'OUT', :occ_after, :occ_rate)
                    """), {
                        "session_id": session_id,
                        "bus_id":     bus_id,
                        "station_id": station_id,
                        "timestamp":  ts,
                        "occ_after":  occ_after,
                        "occ_rate":   occ_rate,
                    })
                occupancy = occ_after
                exit_count += 1
                events_inserted += 1

            # Boardings
            boardings = random_boardings(BASE_BOARDINGS, factor, capacity, occupancy)
            station_boardings = 0
            for _ in range(boardings):
                ts = session_start + timedelta(
                    minutes=random.randint(0, 55),
                    seconds=random.randint(0, 59)
                )
                occ_after = occupancy + 1
                occ_rate  = round((occ_after / capacity) * 100, 2)

                if not dry_run:
                    conn.execute(text("""
                        INSERT INTO passenger_events
                            (session_id, bus_id, station_id, timestamp,
                             direction, occupancy_after_event, occupancy_rate)
                        VALUES
                            (:session_id, :bus_id, :station_id, :timestamp,
                             'IN', :occ_after, :occ_rate)
                    """), {
                        "session_id": session_id,
                        "bus_id":     bus_id,
                        "station_id": station_id,
                        "timestamp":  ts,
                        "occ_after":  occ_after,
                        "occ_rate":   occ_rate,
                    })
                occupancy = occ_after
                entry_count += 1
                station_boardings += 1
                events_inserted += 1

            # Ticket sales for this station-hour
            tickets = ticket_noise(station_boardings)
            if tickets > 0 and not dry_run:
                ticket_ts = session_start + timedelta(minutes=random.randint(5, 55))
                conn.execute(text("""
                    INSERT INTO ticket_sales
                        (bus_id, line_id, station_id, timestamp,
                         tickets_sold, entered_by)
                    VALUES
                        (:bus_id, :line_id, :station_id, :timestamp,
                         :tickets_sold, 'generator')
                """), {
                    "bus_id":       bus_id,
                    "line_id":      line_id,
                    "station_id":   station_id,
                    "timestamp":    ticket_ts,
                    "tickets_sold": tickets,
                })
                tickets_inserted += 1

        # Update session totals
        if not dry_run:
            conn.execute(text("""
                UPDATE sessions
                SET entry_count = :entry_count,
                    exit_count  = :exit_count
                WHERE id = :session_id
            """), {
                "entry_count": entry_count,
                "exit_count":  exit_count,
                "session_id":  session_id,
            })

    return events_inserted, tickets_inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(days: int = 90, dry_run: bool = False) -> None:
    random.seed(42)  # reproducible results

    start_date = date.today() - timedelta(days=days)
    end_date   = date.today() - timedelta(days=1)  # up to yesterday

    logger.info(f"Generating {days} days of data: {start_date} → {end_date}")
    logger.info(f"Buses: {list(BUS_CAPACITY.keys())} | Lines: {list(LINE_STATIONS.keys())}")
    if dry_run:
        logger.info("DRY RUN — nothing will be written to the database")

    engine = init_engine()

    total_events  = 0
    total_tickets = 0
    total_days    = 0

    with engine.begin() as conn:
        if not dry_run:
            seed_master_data(conn)

        current = start_date
        while current <= end_date:
            day_events  = 0
            day_tickets = 0

            for line_id, bus_ids in LINE_BUSES.items():
                for bus_id in bus_ids:
                    e, t = generate_bus_day(conn, current, bus_id, line_id, dry_run)
                    day_events  += e
                    day_tickets += t

            total_events  += day_events
            total_tickets += day_tickets
            total_days    += 1

            if total_days % 10 == 0 or total_days == 1:
                logger.info(
                    f"  Day {total_days:3d}/{days} — {current} | "
                    f"events so far: {total_events:,} | tickets: {total_tickets:,}"
                )

            current += timedelta(days=1)

    logger.info("=" * 55)
    logger.info(f"  Generation complete")
    logger.info(f"  Days generated   : {total_days}")
    logger.info(f"  Passenger events : {total_events:,}")
    logger.info(f"  Ticket rows      : {total_tickets:,}")
    logger.info("=" * 55)

    if not dry_run:
        logger.info("Running ETL to populate analytics tables...")
        import subprocess
        subprocess.run(
            [sys.executable, "-m", "etl.run_etl"],
            cwd=str(Path(__file__).parent.parent),
            check=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SmartTransport synthetic data generator")
    parser.add_argument("--days",    type=int,  default=90,    help="Number of days to generate (default: 90)")
    parser.add_argument("--dry-run", action="store_true",      help="Simulate without writing to DB")
    args = parser.parse_args()
    run(days=args.days, dry_run=args.dry_run)
