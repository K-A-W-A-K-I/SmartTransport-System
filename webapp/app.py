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
    try:
        from database.config import init_engine
        from sqlalchemy import text
        engine = init_engine()
        with engine.connect() as conn:
            n = conn.execute(text(
                "SELECT COUNT(*) FROM recommendations "
                "WHERE severity='CRITICAL' AND status='pending'"
            )).scalar()
        return {"g_critical_alerts": int(n or 0)}
    except Exception:
        return {"g_critical_alerts": 0}


# ── Blueprints ────────────────────────────────────────────────────────────
from webapp.routes.dashboard       import dashboard_bp
from webapp.routes.tickets         import tickets_bp
from webapp.routes.recommendations import recommendations_bp
from webapp.routes.buses           import buses_bp
from webapp.routes.drivers         import drivers_bp
from webapp.routes.activity        import activity_bp
from webapp.routes.settings        import settings_bp
from webapp.routes.search          import search_bp

app.register_blueprint(dashboard_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(recommendations_bp)
app.register_blueprint(buses_bp)
app.register_blueprint(drivers_bp)
app.register_blueprint(activity_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(search_bp)


if __name__ == "__main__":
    app.run(debug=True)
