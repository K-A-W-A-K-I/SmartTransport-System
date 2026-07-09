"""
database/test_db.py
-------------------
Smoke test for the database module.
Run with:  python database/test_db.py

Tests:
  1. Config loads and connection succeeds
  2. Tables are created
  3. A Session row can be inserted and read back
  4. A PassengerEvent row can be inserted and read back
  5. Cleanup — test rows are deleted
"""

import sys
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


def main():
    # ── 1. Config / connection ──────────────────────────────────────────────────
    print("\n── Test 1: connection ──")
    from database.config import verify_connection
    if not verify_connection():
        print("Cannot continue — fix the connection first.")
        sys.exit(1)

    # ── 2. Create tables ────────────────────────────────────────────────────────
    print("\n── Test 2: create tables ──")
    from database.db_client import create_tables
    create_tables()
    print("✓ Tables ready.")

    # ── 3. Insert a Session ─────────────────────────────────────────────────────
    print("\n── Test 3: insert session ──")
    from database.db_client import insert_session

    now = datetime.now(timezone.utc)
    session_data = {
        "session_start": now,
        "session_end":   now + timedelta(seconds=30),
        "mode":          "color",
        "video_file":    "busfinal.mp4",
        "entry_count":   5,
        "exit_count":    3,
    }
    session_id = insert_session(session_data)
    if session_id is None:
        print("✗ Session insert failed.")
        sys.exit(1)
    print(f"✓ Session inserted — id={session_id}")

    # ── 4. Insert a PassengerEvent ──────────────────────────────────────────────
    print("\n── Test 4: insert passenger event ──")
    from database.db_client import insert_event

    event_data = {
        "session_id":            session_id,
        "timestamp":             now + timedelta(seconds=5),
        "direction":             "IN",
        "occupancy_after_event": 1,
        "station_id":            None,
        "bus_id":                None,
    }
    event_id = insert_event(event_data)
    if event_id is None:
        print("✗ Event insert failed.")
        sys.exit(1)
    print(f"✓ PassengerEvent inserted — id={event_id}")

    # ── 5. Read back and verify ─────────────────────────────────────────────────
    print("\n── Test 5: round-trip read ──")
    from database.db_client import get_session
    from database.models import Session as SessionModel, PassengerEvent

    with get_session() as db:
        s = db.get(SessionModel, session_id)
        e = db.get(PassengerEvent, event_id)

        assert s is not None,              "Session not found"
        assert s.mode == "color",          f"mode mismatch: {s.mode}"
        assert s.entry_count == 5,         f"entry_count mismatch: {s.entry_count}"
        assert e is not None,              "Event not found"
        assert e.direction == "IN",        f"direction mismatch: {e.direction}"
        assert e.session_id == session_id, f"session_id mismatch: {e.session_id}"
        print(f"✓ Read back: {s}")
        print(f"✓ Read back: {e}")

    # ── 6. Cleanup ───────────────────────────────────────────────────────────────
    print("\n── Test 6: cleanup ──")
    with get_session() as db:
        ev = db.get(PassengerEvent, event_id)
        se = db.get(SessionModel,   session_id)
        if ev: db.delete(ev)
        if se: db.delete(se)
    print("✓ Test rows deleted.")

    print("\n══ All tests passed ══\n")


if __name__ == "__main__":
    main()
