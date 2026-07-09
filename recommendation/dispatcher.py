"""
recommendation/dispatcher.py
------------------------------
Rule-based recommendation engine for SmartTransport.

Takes predictions from crowd_prediction.py and translates them into
concrete operational actions for the dispatcher.

Rules (in priority order):
  CRITICAL  occupancy >= 95%  → Deploy additional bus immediately
  HIGH      occupancy >= 80%  → Pre-position standby bus
  MEDIUM    occupancy >= 60%  → Monitor closely, alert driver
  RECURRING same slot HIGH 3+ days in a row → Adjust permanent schedule
  LOW_USAGE occupancy <  20%  → Consider reducing frequency / smaller bus
  TICKET    tickets << passengers by >15%  → Fare inspection alert

Usage:
  # Recommend for next 6 hours at all stations
  python -m recommendation.dispatcher

  # Recommend for specific station/line
  python -m recommendation.dispatcher --station 3 --line 2 --hours 8

  # Full network scan for today
  python -m recommendation.dispatcher --network
"""

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.config import init_engine
from prediction.crowd_prediction import CrowdPredictor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("dispatcher")


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

CRITICAL_OCC  = 95.0   # % — deploy extra bus immediately
HIGH_OCC      = 80.0   # % — pre-position standby
MEDIUM_OCC    = 60.0   # % — alert driver
LOW_OCC       = 20.0   # % — consider reducing frequency
TICKET_GAP    = 0.15   # 15% fewer tickets than passengers → fare inspection
RECURRING_DAYS = 3     # same slot HIGH for N days → schedule change


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    priority: str          # CRITICAL / HIGH / MEDIUM / LOW / INFO
    action: str            # short action label
    line_id: int
    line_name: str
    station_id: int
    station_name: str
    hour: int
    expected_occupancy: float
    expected_passengers: int
    message: str
    details: str = ""

    def display(self) -> str:
        icon = {
            "CRITICAL": "🔴",
            "HIGH":     "🟠",
            "MEDIUM":   "🟡",
            "LOW":      "🟢",
            "INFO":     "ℹ️ ",
        }.get(self.priority, "⚪")

        return (
            f"\n{icon} [{self.priority}] {self.action}\n"
            f"   Line     : {self.line_name} (id={self.line_id})\n"
            f"   Station  : {self.station_name} (id={self.station_id})\n"
            f"   Time     : {self.hour:02d}:00 – {(self.hour+1)%24:02d}:00\n"
            f"   Occupancy: {self.expected_occupancy}%  "
            f"({self.expected_passengers} passengers expected)\n"
            f"   ➜ {self.message}\n"
            + (f"   Note     : {self.details}\n" if self.details else "")
        )


# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------

class Dispatcher:
    """
    Loads the prediction model and master data, then applies business rules
    to generate prioritised operational recommendations.
    """

    def __init__(self):
        self.predictor   = CrowdPredictor()
        self.engine      = init_engine()
        self.lines       = self._load_lines()
        self.stations    = self._load_stations()
        self.line_stations = self._load_line_stations()
        logger.info(
            f"Dispatcher ready — "
            f"{len(self.lines)} lines, {len(self.stations)} stations"
        )

    # ── Data loading ────────────────────────────────────────────────────────

    def _load_lines(self) -> dict:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT line_id, line_name, line_number FROM lines")).fetchall()
        return {r[0]: {"name": r[1], "number": r[2]} for r in rows}

    def _load_stations(self) -> dict:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT station_id, station_name FROM stations")).fetchall()
        return {r[0]: r[1] for r in rows}

    def _load_line_stations(self) -> dict[int, list[int]]:
        """Returns {line_id: [station_id, ...]} ordered by stop_order."""
        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT line_id, station_id FROM line_stations ORDER BY line_id, stop_order"
            )).fetchall()
        result: dict[int, list[int]] = {}
        for line_id, station_id in rows:
            result.setdefault(line_id, []).append(station_id)
        return result

    def _load_recent_history(self, station_id: int, line_id: int, hour: int, days: int = 7) -> pd.DataFrame:
        """Load recent historical occupancy for recurrence detection."""
        with self.engine.connect() as conn:
            df = pd.read_sql(text("""
                SELECT date, avg_occupancy_rate
                FROM station_daily_statistics
                WHERE station_id = :sid
                  AND COALESCE(line_id, -1) = :lid
                  AND peak_hour = :hour
                ORDER BY date DESC
                LIMIT :days
            """), conn, params={
                "sid":  station_id,
                "lid":  line_id if line_id else -1,
                "hour": hour,
                "days": days,
            })
        return df

    def _load_ticket_gap(self, station_id: int, line_id: int) -> Optional[float]:
        """
        Returns the average ratio (tickets / passengers) for this station+line.
        None if no data.
        """
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT
                    SUM(t.total_tickets_sold)::float /
                    NULLIF(SUM(s.total_boardings), 0) AS ratio
                FROM ticket_stats t
                JOIN station_daily_statistics s
                    ON  s.date       = t.date
                    AND s.station_id = t.station_id
                    AND COALESCE(s.line_id, -1) = COALESCE(t.line_id, -1)
                WHERE t.station_id = :sid
                  AND COALESCE(t.line_id, -1) = :lid
            """), {"sid": station_id, "lid": line_id if line_id else -1}).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    # ── Rule application ────────────────────────────────────────────────────

    def _apply_rules(
        self,
        pred: dict,
        line_id: int,
        station_id: int,
    ) -> list[Recommendation]:
        """Apply all rules to a single prediction and return recommendations."""
        recs = []
        occ  = pred["expected_occupancy"]
        pax  = pred["expected_passengers"]
        hour = pred["hour"]
        line_name    = self.lines.get(line_id, {}).get("name", f"Line {line_id}")
        station_name = self.stations.get(station_id, f"Station {station_id}")

        # ── Rule 1: CRITICAL occupancy ───────────────────────────────────
        if occ >= CRITICAL_OCC:
            recs.append(Recommendation(
                priority="CRITICAL",
                action="Deploy additional bus immediately",
                line_id=line_id,
                line_name=line_name,
                station_id=station_id,
                station_name=station_name,
                hour=hour,
                expected_occupancy=occ,
                expected_passengers=pax,
                message=(
                    f"Deploy one additional bus on {line_name} "
                    f"for the {hour:02d}:00–{(hour+1)%24:02d}:00 slot."
                ),
                details=f"Predicted occupancy {occ}% exceeds critical threshold of {CRITICAL_OCC}%.",
            ))

        # ── Rule 2: HIGH occupancy ───────────────────────────────────────
        elif occ >= HIGH_OCC:
            # Check if this is a recurring high-occupancy slot
            history = self._load_recent_history(station_id, line_id, hour, days=7)
            high_days = (history["avg_occupancy_rate"] >= HIGH_OCC).sum() if not history.empty else 0

            if high_days >= RECURRING_DAYS:
                recs.append(Recommendation(
                    priority="HIGH",
                    action="Adjust permanent schedule",
                    line_id=line_id,
                    line_name=line_name,
                    station_id=station_id,
                    station_name=station_name,
                    hour=hour,
                    expected_occupancy=occ,
                    expected_passengers=pax,
                    message=(
                        f"Add a permanent bus to {line_name} at {hour:02d}:00. "
                        f"This slot has been over {HIGH_OCC}% for {high_days} of the last 7 days."
                    ),
                    details="Recurring overload — schedule adjustment recommended.",
                ))
            else:
                recs.append(Recommendation(
                    priority="HIGH",
                    action="Pre-position standby bus",
                    line_id=line_id,
                    line_name=line_name,
                    station_id=station_id,
                    station_name=station_name,
                    hour=hour,
                    expected_occupancy=occ,
                    expected_passengers=pax,
                    message=(
                        f"Pre-position a standby bus at {station_name} "
                        f"before {hour:02d}:00 on {line_name}."
                    ),
                    details=f"Predicted occupancy {occ}% is above high threshold {HIGH_OCC}%.",
                ))

        # ── Rule 3: MEDIUM occupancy ─────────────────────────────────────
        elif occ >= MEDIUM_OCC:
            recs.append(Recommendation(
                priority="MEDIUM",
                action="Monitor and alert driver",
                line_id=line_id,
                line_name=line_name,
                station_id=station_id,
                station_name=station_name,
                hour=hour,
                expected_occupancy=occ,
                expected_passengers=pax,
                message=(
                    f"Alert driver on {line_name} to expect higher load at "
                    f"{station_name} around {hour:02d}:00."
                ),
            ))

        # ── Rule 4: LOW usage ────────────────────────────────────────────
        elif occ < LOW_OCC and pax > 0:
            recs.append(Recommendation(
                priority="LOW",
                action="Consider reducing frequency",
                line_id=line_id,
                line_name=line_name,
                station_id=station_id,
                station_name=station_name,
                hour=hour,
                expected_occupancy=occ,
                expected_passengers=pax,
                message=(
                    f"Bus on {line_name} at {hour:02d}:00 expected at only {occ}% capacity. "
                    f"Consider a smaller vehicle or reduced frequency for this slot."
                ),
            ))

        # ── Rule 5: Ticket gap (fare evasion alert) ──────────────────────
        ticket_ratio = self._load_ticket_gap(station_id, line_id)
        if ticket_ratio is not None and ticket_ratio < (1 - TICKET_GAP):
            gap_pct = round((1 - ticket_ratio) * 100, 1)
            recs.append(Recommendation(
                priority="INFO",
                action="Fare inspection recommended",
                line_id=line_id,
                line_name=line_name,
                station_id=station_id,
                station_name=station_name,
                hour=hour,
                expected_occupancy=occ,
                expected_passengers=pax,
                message=(
                    f"Ticket sales at {station_name} on {line_name} are "
                    f"{gap_pct}% below CV passenger counts. "
                    f"Schedule a fare inspection team."
                ),
                details=f"Ticket/passenger ratio: {ticket_ratio:.2f} (threshold: {1-TICKET_GAP:.2f})",
            ))

        return recs

    # ── Persistence ──────────────────────────────────────────────────────────

    def save(self, recs: list[Recommendation], prediction_date=None) -> int:
        """
        Insert recommendations into the recommendations table.
        Skips duplicates (same date + line + station + hour + severity).
        Returns number of rows inserted.
        """
        if not recs:
            return 0

        from datetime import date as date_type
        if prediction_date is None:
            prediction_date = datetime.now().date()

        inserted = 0
        with self.engine.begin() as conn:
            for rec in recs:
                conn.execute(text("""
                    INSERT INTO recommendations
                        (prediction_date, line_id, station_id, hour,
                         predicted_occupancy, predicted_passengers,
                         severity, action, recommendation, status)
                    VALUES
                        (:prediction_date, :line_id, :station_id, :hour,
                         :predicted_occupancy, :predicted_passengers,
                         :severity, :action, :recommendation, 'pending')
                    ON CONFLICT DO NOTHING
                """), {
                    "prediction_date":       prediction_date,
                    "line_id":               rec.line_id if rec.line_id > 0 else None,
                    "station_id":            rec.station_id,
                    "hour":                  rec.hour,
                    "predicted_occupancy":   rec.expected_occupancy,
                    "predicted_passengers":  rec.expected_passengers,
                    "severity":              rec.priority,
                    "action":                rec.action,
                    "recommendation":        rec.message,
                })
                inserted += 1

        logger.info(f"Saved {inserted} recommendations to database.")
        return inserted

    # ── Public API ───────────────────────────────────────────────────────────

    def recommend(
        self,
        station_id: int,
        line_id: int,
        start_hour: int = None,
        hours: int = 6,
        weekday: int = None,
        month: int = None,
    ) -> list[Recommendation]:
        """
        Generate recommendations for a specific station/line over N hours.
        """
        now = datetime.now()
        if start_hour is None:
            start_hour = now.hour
        if weekday is None:
            weekday = now.weekday()
        if month is None:
            month = now.month

        forecasts = self.predictor.predict_next_hours(
            station_id=station_id,
            line_id=line_id,
            weekday=weekday,
            month=month,
            hours=hours,
            start_hour=start_hour,
        )

        all_recs = []
        for pred in forecasts:
            recs = self._apply_rules(pred, line_id, station_id)
            all_recs.extend(recs)

        # Sort by priority
        priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        all_recs.sort(key=lambda r: (priority_order.get(r.priority, 9), r.hour))
        return all_recs

    def network_scan(
        self,
        start_hour: int = None,
        hours: int = 6,
        weekday: int = None,
        month: int = None,
        min_priority: str = "MEDIUM",
    ) -> list[Recommendation]:
        """
        Scan all lines and stations and return recommendations above min_priority.
        """
        now = datetime.now()
        if start_hour is None:
            start_hour = now.hour
        if weekday is None:
            weekday = now.weekday()
        if month is None:
            month = now.month

        priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        threshold = priority_order.get(min_priority, 2)

        all_recs = []
        for line_id, station_ids in self.line_stations.items():
            for station_id in station_ids:
                recs = self.recommend(
                    station_id=station_id,
                    line_id=line_id,
                    start_hour=start_hour,
                    hours=hours,
                    weekday=weekday,
                    month=month,
                )
                filtered = [r for r in recs if priority_order.get(r.priority, 9) <= threshold]
                all_recs.extend(filtered)

        all_recs.sort(key=lambda r: (priority_order.get(r.priority, 9), r.line_id, r.hour))
        return all_recs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SmartTransport Dispatcher")
    parser.add_argument("--station",  type=int, default=None)
    parser.add_argument("--line",     type=int, default=None)
    parser.add_argument("--hour",     type=int, default=None)
    parser.add_argument("--hours",    type=int, default=6)
    parser.add_argument("--weekday",  type=int, default=None, help="0=Mon…6=Sun")
    parser.add_argument("--month",    type=int, default=None)
    parser.add_argument("--network",  action="store_true", help="Scan all lines and stations")
    parser.add_argument("--min",      default="MEDIUM", choices=["CRITICAL","HIGH","MEDIUM","LOW","INFO"])
    args = parser.parse_args()

    dispatcher = Dispatcher()

    if args.network:
        logger.info("Running full network scan...")
        recs = dispatcher.network_scan(
            start_hour=args.hour,
            hours=args.hours,
            weekday=args.weekday,
            month=args.month,
            min_priority=args.min,
        )
    else:
        if args.station is None or args.line is None:
            # Default: scan all lines/stations, show HIGH+ only
            recs = dispatcher.network_scan(
                start_hour=args.hour,
                hours=args.hours,
                weekday=args.weekday,
                month=args.month,
                min_priority="HIGH",
            )
        else:
            recs = dispatcher.recommend(
                station_id=args.station,
                line_id=args.line,
                start_hour=args.hour,
                hours=args.hours,
                weekday=args.weekday,
                month=args.month,
            )

    if not recs:
        print("\n✅ No recommendations — all lines operating within normal parameters.\n")
        return

    # Save to database automatically
    saved = dispatcher.save(recs)

    print(f"\n{'='*55}")
    print(f"  SmartTransport Dispatcher — {len(recs)} Recommendation(s)  [{saved} saved to DB]")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")

    for rec in recs:
        print(rec.display())

    # Summary
    from collections import Counter
    counts = Counter(r.priority for r in recs)
    print(f"{'='*55}")
    print("  Summary:")
    for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
        if counts[level]:
            print(f"    {level:8}: {counts[level]}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
