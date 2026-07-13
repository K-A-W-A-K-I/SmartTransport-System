"""
webapp/services/bus_service.py
"""
import logging
from sqlalchemy import text
from database.config import init_engine

logger = logging.getLogger(__name__)


def _e():
    return init_engine()


def get_buses() -> dict:
    try:
        engine = _e()
        with engine.connect() as conn:

            # ── KPI aggregates ────────────────────────────────────────────
            kpi = conn.execute(text("""
                SELECT
                    COUNT(*)                                            AS total,
                    COUNT(*) FILTER (WHERE status = 'active')          AS active,
                    COUNT(*) FILTER (WHERE status = 'inactive')        AS inactive,
                    ROUND(AVG(capacity)::numeric, 0)                   AS avg_capacity
                FROM buses
            """)).fetchone()

            avg_occ = conn.execute(text("""
                SELECT ROUND(AVG(occ.peak)::numeric, 1) AS avg_occ
                FROM (
                    SELECT bus_id, MAX(CAST(occupancy_rate AS FLOAT)) AS peak
                    FROM passenger_events
                    WHERE timestamp >= CURRENT_DATE AND occupancy_rate IS NOT NULL
                    GROUP BY bus_id
                ) occ
            """)).scalar()

            # ── Main rows ─────────────────────────────────────────────────
            rows = conn.execute(text("""
                SELECT
                    b.bus_id,
                    b.license_plate,
                    b.capacity,
                    b.status,
                    COALESCE(l.line_name,   'Unassigned') AS line_name,
                    COALESCE(l.line_number, '—')          AS line_number,
                    l.line_id,
                    TRIM(COALESCE(d.first_name,'') || ' ' || COALESCE(d.last_name,'')) AS driver_name,
                    d.driver_id,
                    -- peak occupancy today
                    COALESCE((
                        SELECT MAX(pe.occupancy_after_event)
                        FROM passenger_events pe
                        WHERE pe.bus_id = b.bus_id
                          AND pe.timestamp >= CURRENT_DATE
                    ), 0) AS current_occupancy,
                    COALESCE((
                        SELECT ROUND(CAST(MAX(pe.occupancy_rate) AS NUMERIC), 1)
                        FROM passenger_events pe
                        WHERE pe.bus_id = b.bus_id
                          AND pe.timestamp >= CURRENT_DATE
                          AND pe.occupancy_rate IS NOT NULL
                    ), 0) AS occupancy_rate
                FROM buses b
                LEFT JOIN lines   l ON l.line_id   = b.line_id
                LEFT JOIN drivers d ON d.driver_id = b.driver_id
                ORDER BY b.bus_id
            """)).fetchall()

            lines = conn.execute(text(
                "SELECT line_id, line_name, line_number FROM lines ORDER BY line_number"
            )).fetchall()

            drivers = conn.execute(text(
                "SELECT driver_id, "
                "TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS full_name "
                "FROM drivers ORDER BY first_name"
            )).fetchall()

        return {
            "buses":        [dict(r._mapping) for r in rows],
            "lines":        [dict(r._mapping) for r in lines],
            "drivers":      [dict(r._mapping) for r in drivers],
            "kpi": {
                "total":        int(kpi.total),
                "active":       int(kpi.active),
                "inactive":     int(kpi.inactive),
                "avg_capacity": int(kpi.avg_capacity or 0),
                "avg_occ":      float(avg_occ or 0),
            },
            "error": None,
        }
    except Exception as e:
        logger.error(f"get_buses error: {e}")
        return {"buses": [], "lines": [], "drivers": [],
                "kpi": {"total":0,"active":0,"inactive":0,"avg_capacity":0,"avg_occ":0},
                "error": str(e)}


def update_bus(bus_id: int, license_plate: str, capacity: int,
               line_id, driver_id, status: str) -> tuple[bool, str]:
    try:
        engine = _e()
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE buses
                SET license_plate = :lp,
                    capacity      = :cap,
                    line_id       = :line_id,
                    driver_id     = :driver_id,
                    status        = :status
                WHERE bus_id = :bus_id
            """), {
                "bus_id":    bus_id,
                "lp":        license_plate or None,
                "cap":       int(capacity),
                "line_id":   int(line_id)   if line_id   else None,
                "driver_id": int(driver_id) if driver_id else None,
                "status":    status,
            })
        return True, "Bus updated."
    except Exception as e:
        logger.error(f"update_bus error: {e}")
        return False, str(e)
