"""
webapp/routes/activity.py
---------------------------
System Activity feed — Page 6.
"""

from flask import Blueprint, render_template, request
from datetime import date, timedelta
from webapp.services.activity_service import get_activity

activity_bp = Blueprint("activity", __name__, url_prefix="/activity")


@activity_bp.route("/")
def index():
    event_type = request.args.get("type", "all")
    limit      = request.args.get("limit", 100, type=int)
    data       = get_activity(limit=limit, event_type=event_type)
    today     = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    return render_template("activity.html",
                           **data,
                           active_type=event_type,
                           limit=limit,
                           today=today,
                           yesterday=yesterday)
