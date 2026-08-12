"""
generator/generate_realistic_data.py
--------------------------------------
Generates 2 years of realistic synthetic Tunisian urban transport data.

IMPORTANT: This data is SYNTHETIC and designed to represent PLAUSIBLE
Tunisian public transport demand patterns. It does NOT represent official
statistics from TRANSTU, SNTRI, or any other Tunisian transport authority.

Key improvements over the original generator:
  - Seasonal variation (school year vs summer holidays)
  - Monthly demand profiles (Sep–Jun peak, Jul–Aug reduced)
  - Ramadan awareness (evening demand shift, reduced morning peak)
  - Line demand differentiation (high/medium/low demand lines)
  - Station position effects (central > residential > terminal)
  - Realistic occupancy variation (20%–95%, occasional overcrowding)
  - Chronological data (2 full years: Jan 2024 → Dec 2025)
  - Weekday variation (Monday ≠ Tuesday)

Usage:
  python -m generator.generate_realistic_data
  python -m generator.generate_realistic_data --dry-run
"""

import logging
import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from database.config import init_engine

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("realistic_generator")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

START_DATE = date(2024, 1, 1)
END_DATE   = date(2025, 12, 31)

# Bus capacities (unchanged from existing master data)
BUS_CAPACITY = {1: 50, 2: 35, 3: 50, 4: 45, 5: 35, 6: 50, 7: 40, 8: 45}

# Line assignments (unchanged)
LINE_BUSES = {1: [1, 3, 4], 2: [2, 5, 6], 3: [7, 8]}

# Station assignments per line (unchanged — using existing DB)
LINE_STATIONS = {
    1: [17, 18, 2, 20, 5],           # Line 23: Tunis Centre → La Marsa (high demand)
    2: [3, 6, 19, 4, 21],            # Line 42: Bab Saadoun → Ariana (medium demand)
    3: [17, 22, 6, 19, 30, 31, 32],  # Line 15: Bardo → Manouba (lower demand)
}

# Line demand multipliers (differentiated profiles)
LINE_DEMAND = {
    1: 1.35,   # Line 23: Tunis Centre–La Marsa — central, high commuter demand
    2: 1.00,   # Line 42: Bab Saadoun–Ariana — medium commuter demand
    3: 0.72,   # Line 15: Bardo–Manouba — suburban, lower demand
}

# Station position effects (central/interchange vs residential vs terminal)
# Values represent boarding multiplier at this stop
STATION_POSITION_EFFECT = {
    # Line 23 stations
    17: 1.40,   # Tunis Centre — major interchange
    18: 0.85,   # Passage
    2:  1.10,   # Tunis Marine — coastal interchange
    20: 0.75,   # La Goulette
    5:  0.60,   # La Marsa Plage — terminal/residential
    # Line 42 stations
    3:  1.20,   # Bab Saadoun — busy interchange
    6:  0.90,   # Bardo
    19: 0.80,   # Le Bardo
    4:  0.95,   # Ariana Centre
    21: 0.65,   # Ain Zaghouan — residential
    # Line 15 stations
    22: 0.85,   # Cité Sportive
    30: 0.70,   # Manouba Centre — terminal
    31: 0.60,   # Cité El Khadra
    32: 0.55,   # Ibn Khaldoun
}

OPERATING_HOURS = list(range(5, 24))   # 05:00 – 23:00

# Base hourly demand profile (Tunisia: commuter pattern with lunch dip)
BASE_DEMAND = {
    5:  0.20,   # Early morning — low
    6:  0.55,   # Pre-rush warming up
    7:  1.70,   # Morning rush start
    8:  1.95,   # Peak morning rush (workers + students)
    9:  1.40,   # Late morning rush
    10: 0.85,   # Mid-morning
    11: 0.75,   # Late morning
    12: 1.15,   # Lunch movement
    13: 1.20,   # Post-lunch
    14: 0.70,   # Afternoon quiet
    15: 0.85,   # Pre-evening build-up
    16: 1.55,   # Evening rush build
    17: 1.90,   # Peak evening rush
    18: 1.75,   # Evening rush continuing
    19: 1.05,   # Tapering off
    20: 0.65,   # Evening
    21: 0.45,   # Night
    22: 0.30,   # Late night
    23: 0.15,   # Very late
}

# Weekday multipliers (Mon–Sun) — introduces realistic day-to-day variation
WEEKDAY_MULT = {
    0: 1.05,    # Monday — strong commuter demand (week start)
    1: 1.02,    # Tuesday
    2: 1.00,    # Wednesday — baseline
    3: 0.98,    # Thursday
    4: 0.88,    # Friday — reduced (Islamic weekend starts)
    5: 0.55,    # Saturday — light commuter, some leisure
    6: 0.35,    # Sunday — low demand
}

# Monthly seasonal multipliers
# Tunisia: school Sep–Jun, holidays Jul–Aug
MONTHLY_MULT = {
    1:  1.00,   # January — normal work/school
    2:  1.02,   # February
    3:  1.05,   # March
    4:  0.95,   # April — short school break mid-month
    5:  1.00,   # May
    6:  0.85,   # June — end of school year, exams
    7:  0.62,   # July — summer holidays, reduced commuters
    8:  0.58,   # August — peak holidays (lowest demand)
    9:  1.08,   # September — back to school/work surge
    10: 1.05,   # October — full normal activity
    11: 1.03,   # November
    12: 0.90,   # December — end of year, some holidays
}

# Approximate Ramadan months for 2024 and 2025
# 2024: March 11 – April 9
# 2025: March 1 – March 30
RAMADAN_PERIODS = [
    (date(2024, 3, 11), date(2024, 4, 9)),
    (date(2025, 3, 1),  date(2025, 3, 30)),
]

# Public holidays in Tunisia (simplified — just main ones)
PUBLIC_HOLIDAYS = {
    # 2024
    date(2024, 1, 1),   # New Year
    date(2024, 3, 20),  # Independence Day
    date(2024, 4, 9),   # Martyrs' Day
    date(2024, 5, 1),   # Labour Day
    date(2024, 7, 25),  # Republic Day
    date(2024, 8, 13),  # Women's Day
    date(2024, 10, 15), # Evacuation Day
    # 2025
    date(2025, 1, 1),
    date(2025, 3, 20),
    date(2025, 4, 9),
    date(2025, 5, 1),
    date(2025, 7, 25),
    date(2025, 8, 13),
    date(2025, 10, 15),
}

BASE_BOARDINGS = 8   # per stop per hour, before all multipliers


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def is_ramadan(d: date) -> bool:
    for start, end in RAMADAN_PERIODS:
        if start <= d <= end:
            return True
    return False


def ramadan_hour_modifier(hour: int) -> float:
    """
    During Ramadan: morning peak is reduced (fasting), evening peak shifts later.
    Iftar (break fast) around 19:00–20:00 creates a movement surge.
    """
    if 7 <= hour <= 9:
        return 0.65    # reduced morning rush (people tired from fasting)
    elif 12 <= hour <= 14:
        return 0.50    # almost no lunch movement (fasting)
    elif 19 <= hour <= 21:
        return 1.45    # iftar surge — high evening movement
    elif 22 <= hour <= 23:
        return 0.80    # late-night Ramadan activity
    return 1.0


def demand_factor(d: date, hour: int, line_id: int, is_holiday: bool) -> float:
    """Compute composite demand multiplier for a given date/hour/line."""
    if is_holiday:
        return BASE_DEMAND.get(hour, 0.2) * 0.25   # near-zero on public holidays

    base    = BASE_DEMAND.get(hour, 0.2)
    weekday = WEEKDAY_MULT[d.weekday()]
    monthly = MONTHLY_MULT[d.month]
    line    = LINE_DEMAND[line_id]

    # Ramadan modifier
    ram = ramadan_hour_modifier(hour) if is_ramadan(d) else 1.0

    # Micro-variation: random daily noise ±8%
    noise = random.uniform(0.92, 1.08)

    return base * weekday * monthly * line * ram * noise


def station_boarding_factor(station_id: int) -> float:
    return STATION_POSITION_EFFECT.get(station_id, 0.80)


def compute_boardings(base: int, factor: float, capacity: int,
                      occupancy: int, allow_overload: bool = False) -> int:
    """
    Compute realistic boarding count.
    allow_overload: occasionally permits slight overcrowding (up to 105% capacity)
    """
    max_cap = int(capacity * 1.05) if allow_overload else capacity
    space   = max(0, max_cap - occupancy)
    raw     = int(base * factor * random.uniform(0.75, 1.25))
    return min(raw, space)


def compute_alightings(occupancy: int, factor: float) -> int:
    """Alighting rate depends on occupancy and current demand pressure."""
    if occupancy == 0:
        return 0
    # Higher alighting when demand drops (end of rush)
    base_rate = 0.25 + (1.0 - min(factor, 1.5)) * 0.20
    base_rate = max(0.10, min(base_rate, 0.55))
    n = int(occupancy * base_rate * random.uniform(0.80, 1.20))
    return min(n, occupancy)


def ticket_count(boardings: int) -> int:
    """Ticket sales slightly below boardings (fare evasion ~3–8%)."""
    evasion = random.uniform(0.03, 0.08)
    return max(0, int(boardings * (1 - evasion)))


# ---------------------------------------------------------------------------
# Clear existing synthetic data
# ---------------------------------------------------------------------------

def clear_synthetic_data(conn) -> None:
    """
    Delete only synthetic transactional data in FK-safe order.
    Master data (lines, stations, buses, drivers, line_stations) is preserved.
    Uses DELETE instead of TRUNCATE to avoid lock contention.
    """
    logger.info("Clearing existing synthetic data (step 1/6: passenger_events)...")
    conn.execute(text("DELETE FROM passenger_events"))
    logger.info("Clearing (step 2/6: sessions)...")
    conn.execute(text("DELETE FROM sessions"))
    logger.info("Clearing (step 3/6: ticket_sales)...")
    conn.execute(text("DELETE FROM ticket_sales WHERE entered_by LIKE 'generator%' OR entered_by = 'seed_today' OR entered_by = 'realistic_generator'"))
    logger.info("Clearing (step 4/6: etl_watermark)...")
    conn.execute(text("DELETE FROM etl_watermark"))
    logger.info("Clearing (step 5/6: analytics tables)...")
    conn.execute(text("DELETE FROM hourly_station_statistics"))
    conn.execute(text("DELETE FROM line_statistics"))
    conn.execute(text("DELETE FROM bus_statistics"))
    conn.execute(text("DELETE FROM station_daily_statistics"))
    conn.execute(text("DELETE FROM daily_system_statistics"))
    conn.execute(text("DELETE FROM ticket_stats"))
    logger.info("Clearing (step 6/6: forecasts + recommendations)...")
    conn.execute(text("DELETE FROM monthly_forecasts"))
    conn.execute(text("DELETE FROM recommendations"))
    logger.info("Done. Master data preserved.")


# ---------------------------------------------------------------------------
# Generate one bus-day
# ---------------------------------------------------------------------------

def generate_bus_day(conn, sim_date: date, bus_id: int, line_id: int,
                     is_holiday: bool, dry_run: bool) -> tuple[int, int]:

    capacity = BUS_CAPACITY[bus_id]
    stations = LINE_STATIONS[line_id]

    # Start each day with 0–15% occupancy (some passengers already on board)
    occupancy = random.randint(0, int(capacity * 0.15))

    day_events  = 0
    day_tickets = 0

    for hour in OPERATING_HOURS:
        factor = demand_factor(sim_date, hour, line_id, is_holiday)

        session_start = datetime(sim_date.year, sim_date.month, sim_date.day,
                                 hour, 0, 0, tzinfo=timezone.utc)
        session_end   = session_start + timedelta(hours=1)

        entry_count = 0
        exit_count  = 0

        if not dry_run:
            row = conn.execute(text("""
                INSERT INTO sessions
                    (bus_id, session_start, session_end, mode, video_file,
                     entry_count, exit_count)
                VALUES
                    (:bid, :start, :end, 'color', 'realistic_synthetic.mp4', 0, 0)
                RETURNING id
            """), {"bid": bus_id, "start": session_start, "end": session_end}).fetchone()
            session_id = row[0]
        else:
            session_id = 0

        for station_id in stations:
            stn_factor = station_boarding_factor(station_id)

            # Alightings first
            alightings = compute_alightings(occupancy, factor)
            for _ in range(alightings):
                ts = session_start + timedelta(
                    minutes=random.randint(1, 55),
                    seconds=random.randint(0, 59))
                occupancy = max(0, occupancy - 1)
                occ_rate  = round(occupancy / capacity * 100, 2)
                if not dry_run:
                    conn.execute(text("""
                        INSERT INTO passenger_events
                            (session_id, bus_id, station_id, timestamp,
                             direction, occupancy_after_event, occupancy_rate)
                        VALUES (:sid, :bid, :stid, :ts, 'OUT', :occ, :rate)
                    """), {"sid": session_id, "bid": bus_id, "stid": station_id,
                           "ts": ts, "occ": occupancy, "rate": occ_rate})
                exit_count  += 1
                day_events  += 1

            # Boardings — occasionally allow slight overcrowding during peak
            allow_overload = (factor > 1.6 and random.random() < 0.15)
            boarding_base  = int(BASE_BOARDINGS * stn_factor)
            boardings      = compute_boardings(boarding_base, factor, capacity,
                                               occupancy, allow_overload)
            station_boards = 0
            for _ in range(boardings):
                ts = session_start + timedelta(
                    minutes=random.randint(1, 55),
                    seconds=random.randint(0, 59))
                occupancy = min(occupancy + 1, int(capacity * 1.10))  # allow max 110%
                occ_rate  = round(occupancy / capacity * 100, 2)
                if not dry_run:
                    conn.execute(text("""
                        INSERT INTO passenger_events
                            (session_id, bus_id, station_id, timestamp,
                             direction, occupancy_after_event, occupancy_rate)
                        VALUES (:sid, :bid, :stid, :ts, 'IN', :occ, :rate)
                    """), {"sid": session_id, "bid": bus_id, "stid": station_id,
                           "ts": ts, "occ": occupancy, "rate": occ_rate})
                entry_count    += 1
                station_boards += 1
                day_events     += 1

            # Ticket sales
            tix = ticket_count(station_boards)
            if tix > 0 and not dry_run:
                tix_ts = session_start + timedelta(minutes=random.randint(5, 50))
                conn.execute(text("""
                    INSERT INTO ticket_sales
                        (bus_id, line_id, station_id, timestamp,
                         tickets_sold, entered_by)
                    VALUES (:bid, :lid, :stid, :ts, :tix, 'realistic_generator')
                """), {"bid": bus_id, "lid": line_id, "stid": station_id,
                       "ts": tix_ts, "tix": tix})
                day_tickets += 1

        if not dry_run:
            conn.execute(text("""
                UPDATE sessions SET entry_count=:e, exit_count=:x WHERE id=:sid
            """), {"e": entry_count, "x": exit_count, "sid": session_id})

        # Gradual occupancy reset between hours (some passengers alight at stops)
        occupancy = max(0, occupancy - random.randint(2, 6))

    return day_events, day_tickets


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, clear_first: bool = True) -> None:
    random.seed(None)   # real randomness — no fixed seed for realistic variation

    logger.info("=" * 60)
    logger.info("  SmartTransport Realistic Data Generator")
    logger.info(f"  Period: {START_DATE} → {END_DATE}")
    logger.info(f"  DRY RUN: {dry_run}")
    logger.info("  NOTE: Data is SYNTHETIC — not official Tunisian statistics")
    logger.info("=" * 60)

    engine = init_engine()
    total_events  = 0
    total_tickets = 0
    total_days    = 0

    # Skip clearing — just add new data on top of existing
    # The ML model trains on hourly_station_statistics (ETL output), not raw events

    # Generate day by day — each day is its own transaction
    current = START_DATE
    while current <= END_DATE:
        is_holiday = current in PUBLIC_HOLIDAYS
        day_events = day_tickets = 0

        with engine.begin() as conn:
            for line_id, bus_ids in LINE_BUSES.items():
                for bus_id in bus_ids:
                    e, t = generate_bus_day(conn, current, bus_id, line_id,
                                            is_holiday, dry_run)
                    day_events  += e
                    day_tickets += t

        total_events  += day_events
        total_tickets += day_tickets
        total_days    += 1

        if total_days % 30 == 0 or total_days == 1:
            logger.info(
                f"  Day {total_days:3d} — {current} "
                f"({'holiday' if is_holiday else current.strftime('%A')[:3]}) | "
                f"events: {total_events:,} | tickets: {total_tickets:,}"
            )

        current += timedelta(days=1)

    logger.info("=" * 60)
    logger.info(f"  Generation complete")
    logger.info(f"  Days:    {total_days}")
    logger.info(f"  Events:  {total_events:,}")
    logger.info(f"  Tickets: {total_tickets:,}")
    logger.info("=" * 60)

    if not dry_run:
        logger.info("Running ETL pipeline...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "etl.run_etl"],
            cwd=str(Path(__file__).parent.parent)
        )
        if result.returncode == 0:
            logger.info("ETL complete. Now retrain the model:")
            logger.info("  python -m prediction.crowd_prediction --train")
            logger.info("  python -m prediction.ensemble_experiment --save")
            logger.info("  python -m prediction.monthly_forecast --months 6")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate realistic Tunisian transport data (2 years)"
    )
    parser.add_argument("--dry-run",    action="store_true",
                        help="Simulate without writing to DB")
    parser.add_argument("--no-clear",   action="store_true",
                        help="Do not clear existing data first")
    args = parser.parse_args()
    run(dry_run=args.dry_run, clear_first=not args.no_clear)
