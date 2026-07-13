"""
webapp/routes/recommendations.py
----------------------------------
Recommendation Center — Page 3.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from webapp.services.recommendation_service import (
    get_summary, get_recommendations,
    get_recommendation_by_id,
    acknowledge, resolve,
)

recommendations_bp = Blueprint("recommendations", __name__, url_prefix="/recommendations")


@recommendations_bp.route("/")
def index():
    page     = request.args.get("page", 1, type=int)
    severity = request.args.get("severity", "all")
    status   = request.args.get("status", "pending")   # default: show pending
    days     = request.args.get("days", 7, type=int)

    summary = get_summary()
    data    = get_recommendations(page=page, severity=severity,
                                  status=status, days=days)
    return render_template("recommendations.html",
                           **data,
                           summary=summary,
                           filters={"severity": severity,
                                    "status": status,
                                    "days": days})


@recommendations_bp.route("/<int:rec_id>/detail")
def detail(rec_id):
    """JSON endpoint for the detail modal."""
    rec = get_recommendation_by_id(rec_id)
    if not rec:
        return jsonify({"error": "Not found"}), 404
    # Serialize datetime/Decimal fields
    for key, val in rec.items():
        if hasattr(val, 'isoformat'):
            rec[key] = val.isoformat()
        elif hasattr(val, '__float__'):
            rec[key] = float(val)
    return jsonify(rec)


@recommendations_bp.route("/<int:rec_id>/acknowledge", methods=["POST"])
def do_acknowledge(rec_id):
    ok, msg = acknowledge(rec_id)
    flash(msg, "success" if ok else "error")
    return redirect(_back())


@recommendations_bp.route("/<int:rec_id>/resolve", methods=["POST"])
def do_resolve(rec_id):
    ok, msg = resolve(rec_id)
    flash(msg, "success" if ok else "error")
    return redirect(_back())


def _back():
    """Redirect back preserving filters."""
    ref = request.referrer
    return ref if ref else url_for("recommendations.index")
