"""
webapp/routes/search.py
-------------------------
Global search across buses, drivers, stations, recommendations.
"""

from flask import Blueprint, render_template, request
from sqlalchemy import text
from database.config import init_engine

search_bp = Blueprint("search", __name__, url_prefix="/search")


@search_bp.route("/")
def index():
    q = request.args.get("q", "").strip()

    if not q or len(q) < 2:
        return render_template("search.html", q=q, results={}, total=0)

    like = f"%{q}%"
    results = {}
    total   = 0

    try:
        engine = init_engine()
        with engine.connect() as conn:

            # Buses
            buses = conn.execute(text("""
                SELECT b.bus_id, b.license_plate, b.status,
                       COALESCE(l.line_name,'—') AS line_name,
                       COALESCE(l.line_number,'—') AS line_number,
                       TRIM(COALESCE(d.first_name,'') || ' ' || COALESCE(d.last_name,'')) AS driver_name
                FROM buses b
                LEFT JOIN lines   l ON l.line_id   = b.line_id
                LEFT JOIN drivers d ON d.driver_id = b.driver_id
                WHERE b.license_plate ILIKE :q
                   OR l.line_name     ILIKE :q
                   OR l.line_number   ILIKE :q
                LIMIT 10
            """), {"q": like}).fetchall()

            # Drivers
            drivers = conn.execute(text("""
                SELECT d.driver_id,
                       TRIM(COALESCE(d.first_name,'') || ' ' || COALESCE(d.last_name,'')) AS full_name,
                       d.license_number, d.phone, d.status,
                       b.license_plate AS bus_plate
                FROM drivers d
                LEFT JOIN buses b ON b.driver_id = d.driver_id
                WHERE d.first_name    ILIKE :q
                   OR d.last_name     ILIKE :q
                   OR d.license_number ILIKE :q
                   OR d.phone          ILIKE :q
                LIMIT 10
            """), {"q": like}).fetchall()

            # Stations
            stations = conn.execute(text("""
                SELECT station_id, station_name
                FROM stations
                WHERE station_name ILIKE :q
                LIMIT 10
            """), {"q": like}).fetchall()

            # Recommendations
            recs = conn.execute(text("""
                SELECT r.recommendation_id,
                       r.recommendation, r.severity, r.status,
                       r.created_at,
                       COALESCE(s.station_name,'—') AS station_name,
                       COALESCE(l.line_number,'—')  AS line_number
                FROM recommendations r
                LEFT JOIN stations s ON s.station_id = r.station_id
                LEFT JOIN lines    l ON l.line_id    = r.line_id
                WHERE r.recommendation ILIKE :q
                   OR r.action         ILIKE :q
                   OR s.station_name   ILIKE :q
                ORDER BY r.created_at DESC
                LIMIT 10
            """), {"q": like}).fetchall()

        results = {
            "buses":    [dict(r._mapping) for r in buses],
            "drivers":  [dict(r._mapping) for r in drivers],
            "stations": [dict(r._mapping) for r in stations],
            "recs":     [dict(r._mapping) for r in recs],
        }
        total = sum(len(v) for v in results.values())

    except Exception as e:
        results = {"error": str(e)}

    return render_template("search.html", q=q, results=results, total=total)
