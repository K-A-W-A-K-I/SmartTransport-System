"""
webapp/services/driver_service.py
"""
import logging
from sqlalchemy import text
from database.config import init_engine

logger = logging.getLogger(__name__)


def _e():
    return init_engine()


def get_drivers() -> dict:
    try:
        engine = _e()
        with engine.connect() as conn:

            # ── KPI aggregates ────────────────────────────────────────────
            kpi = conn.execute(text("""
                SELECT
                    COUNT(*)                                              AS total,
                    COUNT(*) FILTER (WHERE status = 'on_duty')           AS on_duty,
                    COUNT(*) FILTER (WHERE status = 'available')         AS available,
                    COUNT(*) FILTER (WHERE status NOT IN ('on_duty','available')) AS other
                FROM drivers
            """)).fetchone()

            assigned = conn.execute(text("""
                SELECT COUNT(DISTINCT driver_id)
                FROM buses
                WHERE driver_id IS NOT NULL
            """)).scalar()

            # ── Main rows — one row per driver, first assigned bus ────────
            rows = conn.execute(text("""
                SELECT
                    d.driver_id,
                    d.first_name,
                    d.last_name,
                    TRIM(COALESCE(d.first_name,'') || ' ' || COALESCE(d.last_name,'')) AS full_name,
                    d.license_number,
                    d.phone,
                    d.status,
                    ab.bus_id,
                    ab.license_plate AS bus_plate,
                    COALESCE(l.line_name,   'Unassigned') AS line_name,
                    COALESCE(l.line_number, '—')          AS line_number
                FROM drivers d
                LEFT JOIN LATERAL (
                    SELECT bus_id, license_plate, line_id
                    FROM buses
                    WHERE driver_id = d.driver_id
                    ORDER BY bus_id
                    LIMIT 1
                ) ab ON TRUE
                LEFT JOIN lines l ON l.line_id = ab.line_id
                ORDER BY d.first_name, d.last_name
            """)).fetchall()

            buses = conn.execute(text("""
                SELECT b.bus_id, b.license_plate,
                       COALESCE(l.line_number,'?') AS line_number
                FROM buses b
                LEFT JOIN lines l ON l.line_id = b.line_id
                ORDER BY b.bus_id
            """)).fetchall()

        return {
            "drivers": [dict(r._mapping) for r in rows],
            "buses":   [dict(r._mapping) for r in buses],
            "kpi": {
                "total":    int(kpi.total),
                "assigned": int(assigned or 0),
                "on_duty":  int(kpi.on_duty),
                "available":int(kpi.available),
                "other":    int(kpi.other),
            },
            "error": None,
        }
    except Exception as e:
        logger.error(f"get_drivers error: {e}")
        return {"drivers": [], "buses": [],
                "kpi": {"total":0,"assigned":0,"on_duty":0,"available":0,"other":0},
                "error": str(e)}


def update_driver(driver_id: int, first_name: str, last_name: str,
                  phone: str, license_number: str,
                  bus_id, status: str) -> tuple[bool, str]:
    try:
        engine = _e()
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE drivers
                SET first_name     = :fn,
                    last_name      = :ln,
                    phone          = :phone,
                    license_number = :lic,
                    status         = :status
                WHERE driver_id = :driver_id
            """), {"driver_id": driver_id, "fn": first_name, "ln": last_name or '',
                   "phone": phone or None, "lic": license_number, "status": status})

            # Handle bus assignment
            if bus_id:
                bus_id = int(bus_id)
                # Remove from any other bus
                conn.execute(text("""
                    UPDATE buses SET driver_id = NULL
                    WHERE driver_id = :did AND bus_id != :bid
                """), {"did": driver_id, "bid": bus_id})
                conn.execute(text("""
                    UPDATE buses SET driver_id = :did WHERE bus_id = :bid
                """), {"did": driver_id, "bid": bus_id})
            else:
                conn.execute(text("""
                    UPDATE buses SET driver_id = NULL WHERE driver_id = :did
                """), {"did": driver_id})

        return True, "Driver updated."
    except Exception as e:
        logger.error(f"update_driver error: {e}")
        return False, str(e)
