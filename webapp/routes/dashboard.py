"""
webapp/routes/dashboard.py
---------------------------
Operations Center — Page 1.
"""

from flask import Blueprint, render_template
from webapp.services.dashboard_service import get_dashboard_data

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    data = get_dashboard_data()
    return render_template("dashboard.html", **data)
