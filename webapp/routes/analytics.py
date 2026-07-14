"""
webapp/routes/analytics.py
----------------------------
Analytics landing page — Power BI hub with live ETL status.
"""

from flask import Blueprint, render_template
from sqlalchemy import text
from database.config import init_engine

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@analytics_bp.route("/")
def index():
    status = _get_etl_status()
    return render_template("analytics.html", **status)


def _get_etl_status() -> dict:
    try:
        engine = init_engine()
        with engine.connect() as conn:

            # Last ETL run
            last_run = conn.execute(text("""
                SELECT last_run_at FROM etl_watermark
                WHERE pipeline_name = 'main'
            """)).scalar()

            # Count analytics tables that have data
            table_counts = conn.execute(text("""
                SELECT
                    (SELECT COUNT(*) FROM hourly_station_statistics) AS hss,
                    (SELECT COUNT(*) FROM station_daily_statistics)  AS sds,
                    (SELECT COUNT(*) FROM line_statistics)           AS ls,
                    (SELECT COUNT(*) FROM bus_statistics)            AS bs,
                    (SELECT COUNT(*) FROM daily_system_statistics)   AS dss,
                    (SELECT COUNT(*) FROM ticket_stats)              AS ts
            """)).fetchone()

            tables_with_data = sum(1 for v in table_counts if v and int(v) > 0)

            # Total passengers (all time)
            total_pax = conn.execute(text("""
                SELECT COALESCE(SUM(total_boardings), 0)
                FROM station_daily_statistics
            """)).scalar()

            # Today's passengers
            today_pax = conn.execute(text("""
                SELECT COALESCE(SUM(total_boardings), 0)
                FROM station_daily_statistics
                WHERE date = CURRENT_DATE
            """)).scalar()

        from pathlib import Path
        ml_ready = (Path(__file__).parent.parent.parent /
                    "prediction" / "models" / "crowd_rf.pkl").exists()

        return {
            "db_ok":            True,
            "last_etl":         last_run,
            "analytics_tables": tables_with_data,
            "total_pax":        int(total_pax or 0),
            "today_pax":        int(today_pax or 0),
            "ml_ready":         ml_ready,
            "error":            None,
        }
    except Exception as e:
        return {
            "db_ok":            False,
            "last_etl":         None,
            "analytics_tables": 0,
            "total_pax":        0,
            "today_pax":        0,
            "ml_ready":         False,
            "error":            str(e),
        }
