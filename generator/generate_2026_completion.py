"""
generator/generate_2026_completion.py
--------------------------------------
Generates Aug 13 → Dec 31, 2026 to complete the full year.
Adds on top of existing data — no delete needed.
Uses the same realistic patterns as generate_realistic_data.py.
"""

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Reuse all helpers from the realistic generator
from generator.generate_realistic_data import (
    PUBLIC_HOLIDAYS, LINE_BUSES, generate_bus_day, run as _base_run
)
from database.config import init_engine
from sqlalchemy import text

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("gen_2026_completion")

START_DATE = date(2026, 1, 1)
END_DATE   = date(2026, 4, 7)   # fills gap up to existing April 2026 data


def run() -> None:
    import random
    random.seed(None)

    engine = init_engine()
    total_events = total_tickets = total_days = 0

    current = START_DATE
    while current <= END_DATE:
        is_holiday = current in PUBLIC_HOLIDAYS
        day_events = day_tickets = 0

        with engine.begin() as conn:
            for line_id, bus_ids in LINE_BUSES.items():
                for bus_id in bus_ids:
                    e, t = generate_bus_day(conn, current, bus_id, line_id,
                                            is_holiday, dry_run=False)
                    day_events  += e
                    day_tickets += t

        total_events  += day_events
        total_tickets += day_tickets
        total_days    += 1

        if total_days % 15 == 0 or total_days == 1:
            logger.info(f"  Day {total_days:3d} — {current} | "
                        f"events: {total_events:,} | tickets: {total_tickets:,}")
        current += timedelta(days=1)

    logger.info(f"Done. Days: {total_days} | Events: {total_events:,} | Tickets: {total_tickets:,}")
    logger.info("Running ETL...")

    import subprocess
    subprocess.run([sys.executable, "-m", "etl.run_etl"],
                   cwd=str(Path(__file__).parent.parent))
    logger.info("Refresh Power BI to see full 2026 data.")


if __name__ == "__main__":
    run()
