"""
demo/demo_check.py
-------------------
Pre-demo health check. Run this 5 minutes before presenting.
Verifies every component works end-to-end.

Usage:
    python -m demo.demo_check           # full check
    python -m demo.demo_check --events  # just show latest events
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.config import init_engine
from sqlalchemy import text

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg): print(f"  {RED}✗{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}!{RESET}  {msg}")
def header(msg): print(f"\n{BOLD}{msg}{RESET}")


def check_database():
    header("1. Database connection")
    try:
        engine = init_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        ok("PostgreSQL connected (smart_transport)")
        return engine
    except Exception as e:
        fail(f"Cannot connect to database: {e}")
        sys.exit(1)


def check_tables(engine):
    header("2. Table row counts")
    expected = {
        "passenger_events":          1,
        "sessions":                  1,
        "lines":                     3,
        "buses":                     8,
        "stations":                 15,
        "hourly_station_statistics": 1000,
        "line_statistics":           90,
        "bus_statistics":            90,
        "station_daily_statistics":  500,
        "daily_system_statistics":   30,
        "ticket_sales":              100,
        "ticket_stats":              100,
        "recommendations":           1,
    }

    all_ok = True
    with engine.connect() as conn:
        for tbl, min_rows in expected.items():
            try:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).fetchone()[0]
                if count >= min_rows:
                    ok(f"{tbl:<35} {count:>8,} rows")
                else:
                    warn(f"{tbl:<35} {count:>8,} rows  (expected ≥ {min_rows:,})")
                    all_ok = False
            except Exception as e:
                fail(f"{tbl:<35} ERROR: {e}")
                all_ok = False
    return all_ok


def check_latest_events(engine):
    header("3. Latest passenger events")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT pe.id, pe.direction, pe.occupancy_after_event,
                   pe.occupancy_rate, pe.timestamp, s.station_name
            FROM passenger_events pe
            LEFT JOIN stations s ON s.station_id = pe.station_id
            ORDER BY pe.timestamp DESC
            LIMIT 5
        """)).fetchall()

    if not rows:
        warn("No passenger events found — run main.py first")
        return

    print(f"  {'ID':>6}  {'Dir':>4}  {'Occ':>5}  {'Rate%':>6}  {'Station':<20}  Timestamp")
    print("  " + "-" * 75)
    for r in rows:
        ts = r[4].strftime("%Y-%m-%d %H:%M:%S") if r[4] else "—"
        print(f"  {r[0]:>6}  {r[1]:>4}  {r[2]:>5}  {float(r[3]) if r[3] else 0:>5.1f}%  {str(r[5] or 'Unknown'):<20}  {ts}")


def check_etl(engine):
    header("4. ETL watermark")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT pipeline_name, last_run_at FROM etl_watermark")).fetchone()
    if row:
        ok(f"Last ETL run: {row[1].strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        warn("No watermark — ETL has not run yet. Run: python -m etl.run_etl")


def check_model():
    header("5. Prediction model")
    model_path = Path(__file__).parent.parent / "prediction" / "models" / "crowd_rf.pkl"
    if model_path.exists():
        size_kb = model_path.stat().st_size // 1024
        ok(f"Model file found ({size_kb} KB): {model_path.name}")

        # Quick prediction test
        try:
            from prediction.crowd_prediction import CrowdPredictor
            predictor = CrowdPredictor()
            result = predictor.predict(station_id=3, line_id=2, hour=8, weekday=0, month=7)
            ok(f"Test prediction: {result['expected_passengers']} passengers, "
               f"{result['expected_occupancy']}% occ → {result['risk_level']}")
        except Exception as e:
            fail(f"Prediction failed: {e}")
    else:
        fail(f"Model not found. Run: python -m prediction.crowd_prediction --train")


def check_recommendations(engine):
    header("6. Recommendations")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT severity, status, COUNT(*) as cnt
            FROM recommendations
            GROUP BY severity, status
            ORDER BY severity, status
        """)).fetchall()

    if not rows:
        warn("No recommendations in DB. Run: python -m recommendation.dispatcher --network")
        return

    total = sum(r[2] for r in rows)
    ok(f"Total recommendations: {total}")
    for severity, status, cnt in rows:
        print(f"     {severity:<10} {status:<15} {cnt}")


def check_videos():
    header("7. Video files")
    base = Path(__file__).parent.parent / "data" / "videos"
    for fname in ["busfinal.mp4", "bus.mp4"]:
        p = base / fname
        if p.exists():
            size_mb = p.stat().st_size // (1024 * 1024)
            ok(f"{fname} ({size_mb} MB)")
        else:
            fail(f"{fname} NOT FOUND at {p}")


def print_demo_commands():
    header("Demo commands (copy-paste ready)")
    commands = [
        ("Step 1 — Run CV pipeline",
         "python main.py --mode color --bus-id 1"),
        ("Step 2 — Run ETL",
         "python -m etl.run_etl"),
        ("Step 3 — 8h forecast",
         "python -m prediction.crowd_prediction --forecast --station 3 --line 2 --hour 7 --weekday 0 --month 7 --hours 8"),
        ("Step 4 — Network recommendations",
         "python -m recommendation.dispatcher --network --hour 7 --hours 3 --weekday 0 --month 7 --min HIGH"),
    ]
    for label, cmd in commands:
        print(f"\n  {BOLD}{label}{RESET}")
        print(f"  {YELLOW}{cmd}{RESET}")
    print()


def main():
    parser = argparse.ArgumentParser(description="SmartTransport demo health check")
    parser.add_argument("--events", action="store_true", help="Show latest events only")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  SmartTransport — Demo Health Check")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    engine = check_database()

    if args.events:
        check_latest_events(engine)
        return

    all_tables_ok = check_tables(engine)
    check_latest_events(engine)
    check_etl(engine)
    check_model()
    check_recommendations(engine)
    check_videos()
    print_demo_commands()

    print(f"{'='*55}")
    if all_tables_ok:
        print(f"  {GREEN}{BOLD}✓ System ready for demo{RESET}")
    else:
        print(f"  {YELLOW}{BOLD}! Some checks need attention (see above){RESET}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
