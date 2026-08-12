"""
Generate 2025 historical data (Jan 1 → Dec 31, 2025).
Uses a different random seed to avoid conflicts with existing 2026 data.
Inserts sessions, passenger_events, and ticket_sales for all 8 buses.
"""

import logging
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from database.config import init_engine
from generator.generate_transport_data import (
    BUS_CAPACITY, LINE_BUSES, LINE_STATIONS,
    OPERATING_HOURS, demand_factor, random_boardings,
    random_alightings, ticket_noise
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("gen_2025")

random.seed(99)  # different seed from the 2026 data (seed=42)

START_DATE = date(2025, 1, 1)
END_DATE   = date(2025, 12, 31)


def run():
    engine = init_engine()
    total_events  = 0
    total_tickets = 0
    total_days    = 0

    current = START_DATE
    with engine.begin() as conn:
        while current <= END_DATE:
            day_events  = 0
            day_tickets = 0

            is_weekend = current.weekday() >= 5

            for line_id, bus_ids in LINE_BUSES.items():
                for bus_id in bus_ids:
                    capacity = BUS_CAPACITY[bus_id]
                    stations = LINE_STATIONS[line_id]

                    for hour in OPERATING_HOURS:
                        factor = demand_factor(hour, is_weekend, line_id)
                        session_start = datetime(current.year, current.month,
                                                 current.day, hour, 0, 0,
                                                 tzinfo=timezone.utc)
                        session_end = session_start + timedelta(hours=1)

                        result = conn.execute(text("""
                            INSERT INTO sessions
                                (bus_id, session_start, session_end, mode,
                                 video_file, entry_count, exit_count)
                            VALUES
                                (:bus_id, :start, :end, 'color',
                                 'historical_2025.mp4', 0, 0)
                            RETURNING id
                        """), {"bus_id": bus_id, "start": session_start,
                               "end": session_end}).fetchone()
                        session_id = result[0]

                        entry_count = 0
                        exit_count  = 0
                        occupancy   = random.randint(0, int(capacity * 0.2))

                        for station_id in stations:
                            alightings = random_alightings(occupancy, factor)
                            for _ in range(alightings):
                                ts = session_start + timedelta(
                                    minutes=random.randint(0, 55),
                                    seconds=random.randint(0, 59))
                                occ_after = max(0, occupancy - 1)
                                conn.execute(text("""
                                    INSERT INTO passenger_events
                                        (session_id, bus_id, station_id,
                                         timestamp, direction,
                                         occupancy_after_event, occupancy_rate)
                                    VALUES (:sid, :bid, :stid, :ts, 'OUT',
                                            :occ, :rate)
                                """), {"sid": session_id, "bid": bus_id,
                                       "stid": station_id, "ts": ts,
                                       "occ": occ_after,
                                       "rate": round(occ_after/capacity*100, 2)})
                                occupancy = occ_after
                                exit_count += 1
                                day_events += 1

                            boardings = random_boardings(12, factor, capacity, occupancy)
                            station_boardings = 0
                            for _ in range(boardings):
                                ts = session_start + timedelta(
                                    minutes=random.randint(0, 55),
                                    seconds=random.randint(0, 59))
                                occ_after = occupancy + 1
                                conn.execute(text("""
                                    INSERT INTO passenger_events
                                        (session_id, bus_id, station_id,
                                         timestamp, direction,
                                         occupancy_after_event, occupancy_rate)
                                    VALUES (:sid, :bid, :stid, :ts, 'IN',
                                            :occ, :rate)
                                """), {"sid": session_id, "bid": bus_id,
                                       "stid": station_id, "ts": ts,
                                       "occ": occ_after,
                                       "rate": round(occ_after/capacity*100, 2)})
                                occupancy = occ_after
                                entry_count += 1
                                station_boardings += 1
                                day_events += 1

                            tickets = ticket_noise(station_boardings)
                            if tickets > 0:
                                ticket_ts = session_start + timedelta(
                                    minutes=random.randint(5, 55))
                                conn.execute(text("""
                                    INSERT INTO ticket_sales
                                        (bus_id, line_id, station_id,
                                         timestamp, tickets_sold, entered_by)
                                    VALUES (:bid, :lid, :stid, :ts,
                                            :tix, 'generator_2025')
                                """), {"bid": bus_id, "lid": line_id,
                                       "stid": station_id, "ts": ticket_ts,
                                       "tix": tickets})
                                day_tickets += 1

                        conn.execute(text("""
                            UPDATE sessions
                            SET entry_count=:e, exit_count=:x WHERE id=:sid
                        """), {"e": entry_count, "x": exit_count,
                               "sid": session_id})

            total_events  += day_events
            total_tickets += day_tickets
            total_days    += 1

            if total_days % 30 == 0 or total_days == 1:
                logger.info(f"  Day {total_days:3d}/365 — {current} | "
                            f"events: {total_events:,} | tickets: {total_tickets:,}")

            current += timedelta(days=1)

    logger.info("=" * 55)
    logger.info(f"  2025 generation complete")
    logger.info(f"  Days: {total_days} | Events: {total_events:,} | Tickets: {total_tickets:,}")
    logger.info("=" * 55)
    logger.info("Now run: python -m etl.run_etl")


if __name__ == "__main__":
    run()
