"""
webapp/app.py
-------------
Flask application factory for the SmartTransport Operations Portal.
"""

import sys
from pathlib import Path

# Make sure the project root is on the path so `database/` is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, Blueprint

app = Flask(__name__)
app.secret_key = "smarttransport-dev"

# ── Real blueprints ───────────────────────────────────────────────────────
from webapp.routes.dashboard import dashboard_bp
from webapp.routes.tickets import tickets_bp
from webapp.routes.recommendations import recommendations_bp
from webapp.routes.buses import buses_bp
from webapp.routes.drivers import drivers_bp
app.register_blueprint(dashboard_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(recommendations_bp)
app.register_blueprint(buses_bp)
app.register_blueprint(drivers_bp)

# ── Stub blueprints for pages not yet built ───────────────────────────────
def _stub(name, url_prefix):
    bp = Blueprint(name, __name__)
    @bp.route("/")
    def index():
        return render_template("stub.html", page=name.replace("_", " ").title())
    app.register_blueprint(bp, url_prefix=url_prefix)

_stub("activity", "/activity")


if __name__ == "__main__":
    app.run(debug=True)
