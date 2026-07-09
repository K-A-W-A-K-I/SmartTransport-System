"""
database/connection_test.py
---------------------------
Minimal connection test:
  1. Connect to smart_transport
  2. Insert one session
  3. Read it back
  4. Print it
  5. Clean up

Run with:
    python -m database.connection_test
"""

from datetime import datetime, timezone, timedelta
from database.config import verify_connection
from database.db_client import insert_session, get_session
from database.models import Session as SessionModel


def main():
    print("=" * 45)
    print("  SmartTransport — Database Connection Test")
    print("=" * 45)

    # ── 1. Connect ───────────────────────────────────
    print("\n[1] Connecting to smart_transport ...")
    if not verify_connection():
        raise SystemExit("Connection failed. Check your .env file.")

    # ── 2. Insert ────────────────────────────────────
    print("\n[2] Inserting one session ...")
    now = datetime.now(timezone.utc)
    session_id = insert_session({
        "session_start": now,
        "session_end":   now + timedelta(minutes=3),
        "mode":          "color",
        "video_file":    "busfinal.mp4",
        "entry_count":   12,
        "exit_count":    8,
    })
    print(f"    → Inserted with id = {session_id}")

    # ── 3. Read back ─────────────────────────────────
    print("\n[3] Reading it back ...")
    with get_session() as db:
        row = db.get(SessionModel, session_id)

        # ── 4. Print ─────────────────────────────────────
        print("\n[4] Result:")
        print(f"    id            : {row.id}")
        print(f"    mode          : {row.mode}")
        print(f"    video_file    : {row.video_file}")
        print(f"    session_start : {row.session_start}")
        print(f"    session_end   : {row.session_end}")
        print(f"    entry_count   : {row.entry_count}")
        print(f"    exit_count    : {row.exit_count}")

    # ── 5. Clean up ──────────────────────────────────
    print("\n[5] Cleaning up ...")
    with get_session() as db:
        db.delete(db.get(SessionModel, session_id))
    print("    → Test row deleted.")

    print("\n✓ Database layer is finished.\n")


if __name__ == "__main__":
    main()
