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
    try:
        engine = init_engine()
        with engine.connect() as conn:

            row = conn.execute(text("""
                SELECT occupancy_after_event FROM passenger_events
                ORDER BY timestamp DESC LIMIT 1
            """)).fetchone()
            current_occupancy = int(row[0]) if row else 0

            row = conn.execute(text("""
                SELECT ROUND(AVG(occupancy_rate)::numeric, 1)
                FROM passenger_events
                WHERE timestamp::date = CURRENT_DATE AND occupancy_rate IS NOT NULL
            """)).fetchone()
            avg_occupancy = float(row[0]) if row and row[0] is not None else 0.0

            row = conn.execute(text("""
                SELECT COALESCE(SUM(total_tickets_sold), 0)
                FROM ticket_stats WHERE date = CURRENT_DATE
            """)).fetchone()
            tickets_today = int(row[0]) if row else 0

            row = conn.execute(text("""
                SELECT COUNT(DISTINCT bus_id) FROM sessions
                WHERE session_start::date = CURRENT_DATE AND bus_id IS NOT NULL
            """)).fetchone()
            active_buses = int(row[0]) if row else 0

            row = conn.execute(text(
                "SELECT COUNT(*) FROM recommendations WHERE status = 'pending'"
            )).fetchone()
            pending_recs = int(row[0]) if row else 0

            row = conn.execute(text("""
                SELECT COUNT(*) FROM recommendations
                WHERE severity = 'CRITICAL' AND status = 'pending'
            """)).fetchone()
            critical_alerts = int(row[0]) if row else 0

            # ── Today's Priorities: top 5 pending recs by severity ────────
            priority_rows = conn.execute(text("""
                SELECT r.severity, r.action, r.recommendation,
                       r.predicted_occupancy, r.hour,
                       COALESCE(l.line_name, '—')    AS line_name,
                       COALESCE(l.line_number, '—')  AS line_number,
                       COALESCE(s.station_name, '—') AS station_name,
                       r.recommendation_id
                FROM recommendations r
                LEFT JOIN lines    l ON l.line_id    = r.line_id
                LEFT JOIN stations s ON s.station_id = r.station_id
                WHERE r.status = 'pending'
                ORDER BY
                    CASE r.severity
                        WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM'   THEN 3 ELSE 4 END,
                    r.predicted_occupancy DESC
                LIMIT 5
            """)).fetchall()
            priorities = [dict(r._mapping) for r in priority_rows]

        return {
            "current_occupancy": current_occupancy,
            "avg_occupancy":     avg_occupancy,
            "tickets_today":     tickets_today,
            "active_buses":      active_buses,
            "pending_recs":      pending_recs,
            "critical_alerts":   critical_alerts,
            "priorities":        priorities,
            "error":             None,
        }

    except Exception as e:
        logger.error(f"Dashboard service error: {e}")
        return {
            "current_occupancy": 0, "avg_occupancy": 0.0,
            "tickets_today": 0, "active_buses": 0,
            "pending_recs": 0, "critical_alerts": 0,
            "priorities": [], "error": str(e),
        }
