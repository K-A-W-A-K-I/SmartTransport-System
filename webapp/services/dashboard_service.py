"""
webapp/services/dashboard_service.py
--------------------------------------
Fetches all data needed for the Operations Center dashboard.
All DB queries live here — routes stay clean.
"""

import logging
from sqlalchemy import text
from database.config import init_engine

logger = logging.getLogger(__name__)


def get_dashboard_data() -> dict:
    """
    Returns a dictionary with all KPI values for the dashboard.

    Keys:
        current_occupancy   — latest occupancy_after_event across all buses (int)
        avg_occupancy       — average occupancy_rate from latest session (float %)
        tickets_today       — total tickets sold today (int)
        active_buses        — number of buses that have a session today (int)
        pending_recs        — recommendations with status = 'pending' (int)
        critical_alerts     — recommendations with severity = 'CRITICAL' and status = 'pending' (int)
    """
    try:
        engine = init_engine()
        with engine.connect() as conn:

            # ── Current occupancy: latest single passenger event ──────────
            row = conn.execute(text("""
                SELECT occupancy_after_event
                FROM passenger_events
                ORDER BY timestamp DESC
                LIMIT 1
            """)).fetchone()
            current_occupancy = int(row[0]) if row else 0

            # ── Average occupancy rate: average across today's events ─────
            row = conn.execute(text("""
                SELECT ROUND(AVG(occupancy_rate)::numeric, 1)
                FROM passenger_events
                WHERE timestamp::date = CURRENT_DATE
                  AND occupancy_rate IS NOT NULL
            """)).fetchone()
            avg_occupancy = float(row[0]) if row and row[0] is not None else 0.0

            # ── Tickets today: sum from ticket_stats for today ────────────
            row = conn.execute(text("""
                SELECT COALESCE(SUM(total_tickets_sold), 0)
                FROM ticket_stats
                WHERE date = CURRENT_DATE
            """)).fetchone()
            tickets_today = int(row[0]) if row else 0

            # ── Active buses: buses with at least one session today ───────
            row = conn.execute(text("""
                SELECT COUNT(DISTINCT bus_id)
                FROM sessions
                WHERE session_start::date = CURRENT_DATE
                  AND bus_id IS NOT NULL
            """)).fetchone()
            active_buses = int(row[0]) if row else 0

            # ── Pending recommendations ───────────────────────────────────
            row = conn.execute(text("""
                SELECT COUNT(*)
                FROM recommendations
                WHERE status = 'pending'
            """)).fetchone()
            pending_recs = int(row[0]) if row else 0

            # ── Critical alerts ───────────────────────────────────────────
            row = conn.execute(text("""
                SELECT COUNT(*)
                FROM recommendations
                WHERE severity = 'CRITICAL'
                  AND status = 'pending'
            """)).fetchone()
            critical_alerts = int(row[0]) if row else 0

        return {
            "current_occupancy": current_occupancy,
            "avg_occupancy":     avg_occupancy,
            "tickets_today":     tickets_today,
            "active_buses":      active_buses,
            "pending_recs":      pending_recs,
            "critical_alerts":   critical_alerts,
            "error":             None,
        }

    except Exception as e:
        logger.error(f"Dashboard service error: {e}")
        return {
            "current_occupancy": 0,
            "avg_occupancy":     0.0,
            "tickets_today":     0,
            "active_buses":      0,
            "pending_recs":      0,
            "critical_alerts":   0,
            "error":             str(e),
        }
