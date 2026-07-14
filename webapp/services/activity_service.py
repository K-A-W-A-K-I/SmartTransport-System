"""
webapp/services/activity_service.py
--------------------------------------
Builds a unified activity feed from multiple tables.

Sources:
  - recommendations  → created / acknowledged / resolved
  - ticket_sales     → inserted
  - sessions         → CV session started / completed
  - passenger_events → aggregated per minute (not per event — too noisy)
"""

import logging
from sqlalchemy import text
from database.config import init_engine

logger = logging.getLogger(__name__)


def _e():
    return init_engine()


# Icon + colour per event type
EVENT_META = {
    "recommendation_created":      {"icon": "bi-lightbulb-fill",       "color": "#f57c00", "bg": "#fff3e0"},
    "recommendation_acknowledged": {"icon": "bi-check-circle-fill",     "color": "#1565c0", "bg": "#e3f2fd"},
    "recommendation_resolved":     {"icon": "bi-check2-all",            "color": "#2e7d32", "bg": "#e8f5e9"},
    "ticket_inserted":             {"icon": "bi-ticket-perforated-fill","color": "#8e24aa", "bg": "#f3e5f5"},
    "session_started":             {"icon": "bi-camera-video-fill",     "color": "#00838f", "bg": "#e0f7fa"},
    "session_completed":           {"icon": "bi-camera-video-off-fill", "color": "#546e7a", "bg": "#eceff1"},
}


def get_activity(limit: int = 100, event_type: str = "all") -> dict:
    """
    Returns a unified, time-sorted activity feed.
    event_type: 'all' | 'recommendations' | 'tickets' | 'sessions'
    """
    try:
        engine = _e()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                WITH activity AS (

                    -- Recommendations created
                    SELECT
                        r.created_at                          AS ts,
                        'recommendation_created'              AS event_type,
                        'Recommendation generated'            AS title,
                        r.action || ' — ' ||
                            COALESCE(s.station_name,'?') ||
                            ' / Line ' || COALESCE(l.line_number,'?') AS detail,
                        r.severity                            AS badge,
                        r.recommendation_id::text             AS ref_id
                    FROM recommendations r
                    LEFT JOIN stations s ON s.station_id = r.station_id
                    LEFT JOIN lines    l ON l.line_id    = r.line_id

                    UNION ALL

                    -- Recommendations acknowledged
                    SELECT
                        r.acknowledged_at,
                        'recommendation_acknowledged',
                        'Recommendation acknowledged',
                        r.action || ' — ' ||
                            COALESCE(s.station_name,'?') ||
                            ' / Line ' || COALESCE(l.line_number,'?'),
                        r.severity,
                        r.recommendation_id::text
                    FROM recommendations r
                    LEFT JOIN stations s ON s.station_id = r.station_id
                    LEFT JOIN lines    l ON l.line_id    = r.line_id
                    WHERE r.acknowledged_at IS NOT NULL

                    UNION ALL

                    -- Recommendations resolved
                    SELECT
                        r.resolved_at,
                        'recommendation_resolved',
                        'Recommendation resolved',
                        r.action || ' — ' ||
                            COALESCE(s.station_name,'?') ||
                            ' / Line ' || COALESCE(l.line_number,'?'),
                        r.severity,
                        r.recommendation_id::text
                    FROM recommendations r
                    LEFT JOIN stations s ON s.station_id = r.station_id
                    LEFT JOIN lines    l ON l.line_id    = r.line_id
                    WHERE r.resolved_at IS NOT NULL

                    UNION ALL

                    -- Ticket sales inserted
                    SELECT
                        ts.timestamp,
                        'ticket_inserted',
                        'Ticket sale recorded',
                        ts.tickets_sold::text || ' ticket(s) — ' ||
                            COALESCE(st.station_name,'?') ||
                            ' / Line ' || COALESCE(l.line_number,'?'),
                        NULL,
                        ts.id::text
                    FROM ticket_sales ts
                    LEFT JOIN stations st ON st.station_id = ts.station_id
                    LEFT JOIN lines    l  ON l.line_id     = ts.line_id

                    UNION ALL

                    -- CV Sessions started
                    SELECT
                        se.session_start,
                        'session_started',
                        'CV session started',
                        'Bus ' || COALESCE(b.license_plate, '#'||se.bus_id::text) ||
                            ' — ' || se.mode || ' mode',
                        NULL,
                        se.id::text
                    FROM sessions se
                    LEFT JOIN buses b ON b.bus_id = se.bus_id

                    UNION ALL

                    -- CV Sessions completed
                    SELECT
                        se.session_end,
                        'session_completed',
                        'CV session completed',
                        'Bus ' || COALESCE(b.license_plate, '#'||se.bus_id::text) ||
                            ' — IN ' || se.entry_count ||
                            ' / OUT ' || se.exit_count,
                        NULL,
                        se.id::text
                    FROM sessions se
                    LEFT JOIN buses b ON b.bus_id = se.bus_id

                )
                SELECT *
                FROM activity
                WHERE ts IS NOT NULL
                  AND (:event_type = 'all'
                       OR (:event_type = 'recommendations' AND event_type LIKE 'recommendation%')
                       OR (:event_type = 'tickets'         AND event_type = 'ticket_inserted')
                       OR (:event_type = 'sessions'        AND event_type LIKE 'session%')
                      )
                ORDER BY ts DESC
                LIMIT :limit
            """), {"limit": limit, "event_type": event_type}).fetchall()

        events = []
        for r in rows:
            row = dict(r._mapping)
            meta = EVENT_META.get(row["event_type"], {
                "icon": "bi-circle-fill", "color": "#6c7a8d", "bg": "#f0f4f8"
            })
            row.update(meta)
            events.append(row)

        return {"events": events, "error": None}

    except Exception as e:
        logger.error(f"get_activity error: {e}")
        return {"events": [], "error": str(e)}
