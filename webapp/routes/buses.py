from flask import Blueprint, render_template, request, redirect, url_for, flash
from webapp.services.bus_service import get_buses, update_bus

buses_bp = Blueprint("buses", __name__, url_prefix="/buses")


@buses_bp.route("/")
def index():
    data = get_buses()
    return render_template("buses.html", **data)


@buses_bp.route("/<int:bus_id>/edit", methods=["POST"])
def edit(bus_id):
    ok, msg = update_bus(
        bus_id        = bus_id,
        license_plate = request.form.get("license_plate"),
        capacity      = request.form.get("capacity"),
        line_id       = request.form.get("line_id") or None,
        driver_id     = request.form.get("driver_id") or None,
        status        = request.form.get("status", "active"),
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("buses.index"))
