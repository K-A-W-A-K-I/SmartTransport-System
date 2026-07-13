"""
webapp/routes/tickets.py
--------------------------
Ticket Management — Page 2.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import date
from webapp.services.ticket_service import (
    get_tickets, get_ticket_by_id,
    get_stations, get_lines, get_lines_for_station, get_buses,
    create_ticket, update_ticket, delete_ticket,
)

tickets_bp = Blueprint("tickets", __name__, url_prefix="/tickets")


@tickets_bp.route("/")
def index():
    page       = request.args.get("page", 1, type=int)
    station_id = request.args.get("station_id", type=int)
    line_id    = request.args.get("line_id", type=int)
    # Default: today. Pass show_all=1 to remove the date restriction.
    show_all   = request.args.get("show_all", "0") == "1"
    today      = date.today().isoformat()
    date_from  = None if show_all else today
    date_to    = None if show_all else today

    data     = get_tickets(page=page, station_id=station_id, line_id=line_id,
                           date_from=date_from, date_to=date_to)
    stations = get_stations()

    return render_template("tickets.html",
                           **data,
                           stations=stations,
                           show_all=show_all,
                           today=today,
                           filters={"station_id": station_id, "line_id": line_id})


@tickets_bp.route("/lines-for-station")
def lines_for_station():
    """JSON endpoint: returns lines that serve a given station."""
    station_id = request.args.get("station_id", type=int)
    if not station_id:
        return jsonify([])
    return jsonify(get_lines_for_station(station_id))


@tickets_bp.route("/create", methods=["POST"])
def create():
    ok, msg = create_ticket(
        station_id   = request.form.get("station_id"),
        line_id      = request.form.get("line_id"),
        bus_id       = request.form.get("bus_id") or None,
        tickets_sold = request.form.get("tickets_sold"),
        timestamp    = request.form.get("timestamp"),
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("tickets.index"))


@tickets_bp.route("/<int:ticket_id>/edit", methods=["POST"])
def edit(ticket_id):
    ok, msg = update_ticket(
        ticket_id    = ticket_id,
        station_id   = request.form.get("station_id"),
        line_id      = request.form.get("line_id"),
        bus_id       = request.form.get("bus_id") or None,
        tickets_sold = request.form.get("tickets_sold"),
        timestamp    = request.form.get("timestamp"),
    )
    flash(msg, "success" if ok else "error")
    return redirect(url_for("tickets.index"))


@tickets_bp.route("/<int:ticket_id>/delete", methods=["POST"])
def delete(ticket_id):
    ok, msg = delete_ticket(ticket_id)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("tickets.index"))
