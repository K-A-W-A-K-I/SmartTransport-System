"""
webapp/services/recommendation_service.py
-------------------------------------------
All DB logic for the Recommendation Center.
"""

import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from database.config import init_engine

logger = logging.getLogger(__name__)


def _engine():
    return init_engine()


# ── Summary counts ────────────────────────────────────────────────────────

def get_summary() -> dict:
    """Return counts by status + critical pending count."""
    try:
        engine = _engine()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT status, COUNT(*) AS cnt
                FROM recommendations
                GROUP BY status
            """)).fetchall()
            critical = conn.execute(text("""
                SELECT COUNT(*) FROM recommendations
                WHERE severity = 'CRITICAL' AND status = 'pending'
            """)).scalar()

        counts = {"pending": 0, "acknowledged": 0, "resolved": 0}
        for r in rows:
            if r[0] in counts:
                counts[r[0]] = int(r[1])
        counts["critical"] = int(critical or 0)
        return counts
    except Exception as e:
        logger.error(f"get_summary error: {e}")
        return {"pending": 0, "acknowledged": 0, "resolved": 0, "critical": 0}


# ── List with filters ─────────────────────────────────────────────────────

def get_recommendations(page: int = 1, per_page: int = 20,
                        severity: str = None, status: str = None,
                        days: int = 7) -> dict:
    """
    Paginated recommendations with station/line names.
    days=0 means no date filter (all time).
    """
    filters = []
    params  = {"limit": per_page, "offset": (page - 1) * per_page}

    if severity and severity != "all":
        filters.append("r.severity = :severity")
        params["severity"] = severity.upper()

    if status and status != "all":
        filters.append("r.status = :status")
        params["status"] = status.lower()

    if days and int(days) > 0:
        filters.append("r.created_at >= NOW() - INTERVAL ':days days'")
        # use text concat to avoid bind param in INTERVAL
        since = datetime.now(timezone.utc) - timedelta(days=int(days))
        filters[-1] = "r.created_at >= :since"
        params["since"] = since

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    query = text(f"""
        SELECT
            r.recommendation_id,
            r.created_at,
            r.prediction_date,
            r.hour,
            COALESCE(l.line_name, 'Unknown')    AS line_name,
            COALESCE(l.line_number, '—')         AS line_number,
            COALESCE(s.station_name, 'Unknown')  AS station_name,
            r.predicted_occupancy,
            r.predicted_passengers,
            r.severity,
            r.action,
            r.recommendation,
            r.status,
            r.acknowledged_at,
            r.resolved_at,
            r.line_id,
            r.station_id
        FROM recommendations r
        LEFT JOIN lines    l ON l.line_id    = r.line_id
        LEFT JOIN stations s ON s.station_id = r.station_id
        {where}
        ORDER BY
            CASE r.severity
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH'     THEN 2
                WHEN 'MEDIUM'   THEN 3
                WHEN 'LOW'      THEN 4
                ELSE 5
            END,
            r.created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    count_q = text(f"""
        SELECT COUNT(*) FROM recommendations r {where}
    """)

    try:
        engine = _engine()
        with engine.connect() as conn:
            rows  = conn.execute(query, params).fetchall()
            count_params = {k: v for k, v in params.items()
                            if k not in ("limit", "offset")}
            total = conn.execute(count_q, count_params).scalar()

        recs = [dict(r._mapping) for r in rows]
        total_pages = max(1, -(-total // per_page))
        return {"recommendations": recs, "total": int(total),
                "page": page, "total_pages": total_pages, "error": None}
    except Exception as e:
        logger.error(f"get_recommendations error: {e}")
        return {"recommendations": [], "total": 0, "page": 1,
                "total_pages": 1, "error": str(e)}


# ── Single recommendation (for detail modal) ──────────────────────────────

def get_recommendation_by_id(rec_id: int) -> dict | None:
    try:
        engine = _engine()
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT
                    r.*,
                    COALESCE(l.line_name,    'Unknown') AS line_name,
                    COALESCE(l.line_number,  '—')        AS line_number,
                    COALESCE(s.station_name, 'Unknown') AS station_name,
                    -- current occupancy: latest event at this station
                    (SELECT pe.occupancy_rate
                     FROM passenger_events pe
                     WHERE pe.station_id = r.station_id
                     ORDER BY pe.timestamp DESC
                     LIMIT 1) AS current_occupancy
                FROM recommendations r
                LEFT JOIN lines    l ON l.line_id    = r.line_id
                LEFT JOIN stations s ON s.station_id = r.station_id
                WHERE r.recommendation_id = :id
            """), {"id": rec_id}).fetchone()
        return dict(row._mapping) if row else None
    except Exception as e:
        logger.error(f"get_recommendation_by_id error: {e}")
        return None


# ── Status transitions ────────────────────────────────────────────────────

def acknowledge(rec_id: int) -> tuple[bool, str]:
    try:
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE recommendations
                SET status          = 'acknowledged',
                    acknowledged_at = NOW()
                WHERE recommendation_id = :id
                  AND status = 'pending'
            """), {"id": rec_id})
        return True, "Recommendation acknowledged."
    except Exception as e:
        logger.error(f"acknowledge error: {e}")
        return False, str(e)


def resolve(rec_id: int) -> tuple[bool, str]:
    try:
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE recommendations
                SET status      = 'resolved',
                    resolved_at = NOW()
                WHERE recommendation_id = :id
                  AND status IN ('pending', 'acknowledged')
            """), {"id": rec_id})
        return True, "Recommendation resolved."
    except Exception as e:
        logger.error(f"resolve error: {e}")
        return False, str(e)
