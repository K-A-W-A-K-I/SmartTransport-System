"""
webapp/routes/profile.py
--------------------------
Operator profile page — all data from .env and live DB.
"""

import os
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from dotenv import load_dotenv, set_key
from pathlib import Path
from sqlalchemy import text
from database.config import init_engine

profile_bp = Blueprint("profile", __name__, url_prefix="/profile")

ENV_PATH = Path(__file__).parent.parent.parent / ".env"


@profile_bp.route("/")
def index():
    stats = _get_live_stats()
    return render_template("profile.html", **stats)


@profile_bp.route("/update", methods=["POST"])
def update():
    """Save operator profile fields back to .env."""
    load_dotenv(ENV_PATH)
    fields = {
        "OPERATOR_NAME":     request.form.get("name",     "").strip(),
        "OPERATOR_ROLE":     request.form.get("role",     "").strip(),
        "OPERATOR_TERMINAL": request.form.get("terminal", "").strip(),
        "OPERATOR_EMAIL":    request.form.get("email",    "").strip(),
        "OPERATOR_PHONE":    request.form.get("phone",    "").strip(),
    }
    for key, value in fields.items():
        if value:
            set_key(str(ENV_PATH), key, value)
    flash("Profile updated successfully.", "success")
    return redirect(url_for("profile.index"))


def _get_live_stats() -> dict:
    """Pull live activity stats from the database."""
    try:
        engine = init_engine()
        with engine.connect() as conn:

            # Sessions today
            sessions_today = conn.execute(text("""
                SELECT COUNT(*) FROM sessions
                WHERE session_start::date = CURRENT_DATE
            """)).scalar()

            # Passengers counted today
            pax_today = conn.execute(text("""
                SELECT COALESCE(SUM(entry_count), 0)
                FROM sessions
                WHERE session_start::date = CURRENT_DATE
            """)).scalar()

            # Tickets entered today (via portal)
            tickets_today = conn.execute(text("""
                SELECT COALESCE(COUNT(*), 0) FROM ticket_sales
                WHERE timestamp::date = CURRENT_DATE
                  AND entered_by = 'portal'
            """)).scalar()

            # Recommendations handled today
            recs_handled = conn.execute(text("""
                SELECT COALESCE(COUNT(*), 0) FROM recommendations
                WHERE (acknowledged_at::date = CURRENT_DATE
                    OR resolved_at::date = CURRENT_DATE)
            """)).scalar()

            # All-time recommendations resolved
            recs_resolved = conn.execute(text("""
                SELECT COUNT(*) FROM recommendations WHERE status = 'resolved'
            """)).scalar()

            # All-time pending
            recs_pending = conn.execute(text("""
                SELECT COUNT(*) FROM recommendations WHERE status = 'pending'
            """)).scalar()

            # Last activity timestamp
            last_activity = conn.execute(text("""
                SELECT MAX(session_start) FROM sessions
            """)).scalar()

            # Total passengers all time
            total_pax = conn.execute(text("""
                SELECT COALESCE(SUM(total_boardings), 0)
                FROM station_daily_statistics
            """)).scalar()

        return {
            "sessions_today":  int(sessions_today or 0),
            "pax_today":       int(pax_today or 0),
            "tickets_today":   int(tickets_today or 0),
            "recs_handled":    int(recs_handled or 0),
            "recs_resolved":   int(recs_resolved or 0),
            "recs_pending":    int(recs_pending or 0),
            "last_activity":   last_activity,
            "total_pax":       int(total_pax or 0),
            "today":           date.today(),
            "db_error":        None,
        }
    except Exception as e:
        return {
            "sessions_today": 0, "pax_today": 0, "tickets_today": 0,
            "recs_handled": 0, "recs_resolved": 0, "recs_pending": 0,
            "last_activity": None, "total_pax": 0,
            "today": date.today(), "db_error": str(e),
        }
