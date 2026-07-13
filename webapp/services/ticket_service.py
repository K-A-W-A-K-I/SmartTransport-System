"""
webapp/services/ticket_service.py
-----------------------------------
All DB logic for Ticket Management.
Routes stay clean — no SQL outside this file.
"""

import logging
from datetime import datetime, timezone
from sqlalchemy import text
from database.config import init_engine

logger = logging.getLogger(__name__)


def _engine():
    return init_engine()


# ── Read ──────────────────────────────────────────────────────────────────

def get_tickets(page: int = 1, per_page: int = 24,
                station_id: int = None, line_id: int = None,
                date_from: str = None, date_to: str = None) -> dict:
    """
    Returns paginated ticket sales with station/line names joined.
    Filters: station_id, line_id, date_from (YYYY-MM-DD), date_to (YYYY-MM-DD).
    """
    filters = []
    params  = {"limit": per_page, "offset": (page - 1) * per_page}

    if station_id:
        filters.append("ts.station_id = :station_id")
        params["station_id"] = station_id
    if line_id:
        filters.append("ts.line_id = :line_id")
        params["line_id"] = line_id
    if date_from:
        filters.append("ts.timestamp::date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        filters.append("ts.timestamp::date <= :date_to")
        params["date_to"] = date_to

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    query = text(f"""
        SELECT
            ts.id,
            ts.timestamp,
            COALESCE(s.station_name, 'Unknown')  AS station_name,
            COALESCE(l.line_name,    'Unknown')  AS line_name,
            ts.tickets_sold,
            ts.station_id,
            ts.line_id,
            ts.bus_id,
            ts.entered_by
        FROM ticket_sales ts
        LEFT JOIN stations s ON s.station_id = ts.station_id
        LEFT JOIN lines    l ON l.line_id    = ts.line_id
        {where}
        ORDER BY ts.timestamp DESC
        LIMIT :limit OFFSET :offset
    """)

    count_query = text(f"""
        SELECT COUNT(*)
        FROM ticket_sales ts
        {where}
    """)

    try:
        engine = _engine()
        with engine.connect() as conn:
            rows  = conn.execute(query, params).fetchall()
            total = conn.execute(count_query, {k: v for k, v in params.items()
                                               if k not in ("limit", "offset")}).scalar()
        tickets = [dict(r._mapping) for r in rows]
        total_pages = max(1, -(-total // per_page))  # ceiling division
        return {"tickets": tickets, "total": total,
                "page": page, "total_pages": total_pages, "error": None}
    except Exception as e:
        logger.error(f"get_tickets error: {e}")
        return {"tickets": [], "total": 0, "page": 1,
                "total_pages": 1, "error": str(e)}


def get_ticket_by_id(ticket_id: int) -> dict | None:
    try:
        engine = _engine()
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT ts.id, ts.timestamp, ts.tickets_sold,
                       ts.station_id, ts.line_id, ts.bus_id, ts.entered_by
                FROM ticket_sales ts
                WHERE ts.id = :id
            """), {"id": ticket_id}).fetchone()
        return dict(row._mapping) if row else None
    except Exception as e:
        logger.error(f"get_ticket_by_id error: {e}")
        return None


def get_stations() -> list:
    try:
        engine = _engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT station_id, station_name FROM stations ORDER BY station_name"
            )).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        logger.error(f"get_stations error: {e}")
        return []


def get_lines() -> list:
    try:
        engine = _engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT line_id, line_name, line_number FROM lines ORDER BY line_number"
            )).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        logger.error(f"get_lines error: {e}")
        return []


def get_lines_for_station(station_id: int) -> list:
    """Return only lines that serve a given station (via line_stations)."""
    try:
        engine = _engine()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT l.line_id, l.line_name, l.line_number
                FROM lines l
                JOIN line_stations ls ON ls.line_id = l.line_id
                WHERE ls.station_id = :station_id
                ORDER BY l.line_number
            """), {"station_id": station_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        logger.error(f"get_lines_for_station error: {e}")
        return []


def get_buses() -> list:
    try:
        engine = _engine()
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT bus_id, license_plate FROM buses ORDER BY bus_id"
            )).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        logger.error(f"get_buses error: {e}")
        return []


# ── Create ────────────────────────────────────────────────────────────────

def create_ticket(station_id: int, line_id: int, bus_id: int,
                  tickets_sold: int, timestamp: str,
                  entered_by: str = "portal") -> tuple[bool, str]:
    try:
        ts = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ticket_sales
                    (station_id, line_id, bus_id, timestamp, tickets_sold, entered_by)
                VALUES
                    (:station_id, :line_id, :bus_id, :timestamp, :tickets_sold, :entered_by)
            """), {
                "station_id":   int(station_id),
                "line_id":      int(line_id),
                "bus_id":       int(bus_id) if bus_id else None,
                "timestamp":    ts,
                "tickets_sold": int(tickets_sold),
                "entered_by":   entered_by,
            })
        return True, "Ticket sale added successfully."
    except Exception as e:
        logger.error(f"create_ticket error: {e}")
        return False, str(e)


# ── Update ────────────────────────────────────────────────────────────────

def update_ticket(ticket_id: int, station_id: int, line_id: int,
                  bus_id: int, tickets_sold: int, timestamp: str) -> tuple[bool, str]:
    try:
        ts = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE ticket_sales
                SET station_id   = :station_id,
                    line_id      = :line_id,
                    bus_id       = :bus_id,
                    timestamp    = :timestamp,
                    tickets_sold = :tickets_sold
                WHERE id = :id
            """), {
                "id":           ticket_id,
                "station_id":   int(station_id),
                "line_id":      int(line_id),
                "bus_id":       int(bus_id) if bus_id else None,
                "timestamp":    ts,
                "tickets_sold": int(tickets_sold),
            })
        return True, "Ticket sale updated."
    except Exception as e:
        logger.error(f"update_ticket error: {e}")
        return False, str(e)


# ── Delete ────────────────────────────────────────────────────────────────

def delete_ticket(ticket_id: int) -> tuple[bool, str]:
    try:
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(text(
                "DELETE FROM ticket_sales WHERE id = :id"
            ), {"id": ticket_id})
        return True, "Ticket sale deleted."
    except Exception as e:
        logger.error(f"delete_ticket error: {e}")
        return False, str(e)
