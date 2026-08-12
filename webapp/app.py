"""
webapp/app.py
-------------
Flask application factory for the SmartTransport Operations Portal.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template

app = Flask(__name__)
app.secret_key = "smarttransport-dev"


# ── Context processor — injects live globals into every template ──────────
@app.context_processor
def inject_globals():
    import os
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env")

    # Operator profile from .env
    op_name     = os.getenv("OPERATOR_NAME",    "Ops Manager")
    op_role     = os.getenv("OPERATOR_ROLE",    "Operations Manager")
    op_terminal = os.getenv("OPERATOR_TERMINAL","HQ Terminal")
    op_email    = os.getenv("OPERATOR_EMAIL",   "")
    op_phone    = os.getenv("OPERATOR_PHONE",   "")
    # Avatar initials: first letter of each word in name
    initials = "".join(w[0].upper() for w in op_name.split()[:2])

    # Live stats for the profile page
    try:
        from database.config import init_engine
        from sqlalchemy import text
        engine = init_engine()
        with engine.connect() as conn:
            n_critical = conn.execute(text(
                "SELECT COUNT(*) FROM recommendations "
                "WHERE severity='CRITICAL' AND status='pending'"
            )).scalar()
            n_pending = conn.execute(text(
                "SELECT COUNT(*) FROM recommendations WHERE status='pending'"
            )).scalar()
            n_resolved = conn.execute(text(
                "SELECT COUNT(*) FROM recommendations WHERE status='resolved'"
            )).scalar()
            sessions_today = conn.execute(text(
                "SELECT COUNT(*) FROM sessions "
                "WHERE session_start::date = CURRENT_DATE"
            )).scalar()
        g_critical_alerts = int(n_critical or 0)
    except Exception:
        n_pending = n_resolved = sessions_today = 0
        g_critical_alerts = 0

    return {
        "g_critical_alerts": g_critical_alerts,
        "op_name":           op_name,
        "op_role":           op_role,
        "op_terminal":       op_terminal,
        "op_email":          op_email,
        "op_phone":          op_phone,
        "op_initials":       initials,
        "op_pending":        int(n_pending or 0),
        "op_resolved":       int(n_resolved or 0),
        "op_sessions_today": int(sessions_today or 0),
    }


# ── Blueprints ────────────────────────────────────────────────────────────
from webapp.routes.dashboard       import dashboard_bp
from webapp.routes.tickets         import tickets_bp
from webapp.routes.recommendations import recommendations_bp
from webapp.routes.buses           import buses_bp
from webapp.routes.drivers         import drivers_bp
from webapp.routes.activity        import activity_bp
from webapp.routes.settings        import settings_bp
from webapp.routes.search          import search_bp
from webapp.routes.analytics       import analytics_bp
from webapp.routes.profile         import profile_bp

app.register_blueprint(dashboard_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(recommendations_bp)
app.register_blueprint(buses_bp)
app.register_blueprint(drivers_bp)
app.register_blueprint(activity_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(search_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(profile_bp)


if __name__ == "__main__":
    app.run(debug=True)
