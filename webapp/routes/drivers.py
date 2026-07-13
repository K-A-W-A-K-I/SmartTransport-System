from flask import Blueprint, render_template, request, redirect, url_for, flash
from webapp.services.driver_service import get_drivers, update_driver

drivers_bp = Blueprint("drivers", __name__, url_prefix="/drivers")


@drivers_bp.route("/")
def index():
    data = get_drivers()
    return render_template("drivers.html", **data)


@drivers_bp.route("/<int:driver_id>/edit", methods=["POST"])
def edit(driver_id):
    ok, msg = update_driver(
        driver_id      = driver_id,
        first_name     = request.form.get("first_name"),
        last_name      = request.form.get("last_name"),
        phone          = request.form.get("phone"),
        license_number = request.form.get("license_number"),
        bus_id         = request.form.get("bus_id") or None,
        status         = request.form.get("status", "available"),
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("drivers.index"))
