"""
prediction/monthly_forecast.py
--------------------------------
Generates monthly passenger/occupancy forecasts per line for Power BI Page 3.

Usage:
    python -m prediction.monthly_forecast
    python -m prediction.monthly_forecast --months 6
"""

import argparse
import logging
import pickle
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from calendar import monthrange

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("monthly_forecast")

MODEL_DIR  = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / "crowd_rf.pkl"
META_PATH  = MODEL_DIR / "crowd_meta.pkl"

RISK_ACTIONS = {
    "CRITICAL": "Deploy additional bus immediately",
    "HIGH":     "Pre-position standby bus",
    "MEDIUM":   "Monitor closely — alert drivers",
    "LOW":      "Standard operations",
}

HOURS    = list(range(6, 23))   # 17 hours
WEEKDAYS = list(range(7))       # 7 days


def load_model():
    """Load model and force n_jobs=1 to avoid multiprocessing hang."""
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    # Set n_jobs=1 on each sub-estimator to avoid spawning processes
    try:
        for est in model.estimators_:
            est.n_jobs = 1
    except Exception:
        pass
    with open(META_PATH, "rb") as f:
        meta = pickle.load(f)
    return model, meta


def get_lines_stations(engine) -> list[dict]:
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT ls.line_id, ls.station_id
            FROM line_stations ls
            ORDER BY ls.line_id, ls.station_id
        """)).fetchall()
    return [{"line_id": r[0], "station_id": r[1]} for r in rows]


def run(months_ahead: int = 6) -> None:
    from database.config import init_engine
    from sqlalchemy import text

    logger.info(f"Generating monthly forecasts ({months_ahead} months)...")

    if not MODEL_PATH.exists():
        logger.error("Model not found. Run: python -m prediction.crowd_prediction --train")
        sys.exit(1)

    model, meta = load_model()
    engine      = init_engine()
    pairs       = get_lines_stations(engine)

    if not pairs:
        logger.error("No line_stations found.")
        return

    n_pairs      = len(pairs)
    n_slots      = len(WEEKDAYS) * len(HOURS)
    today        = date.today()
    total_saved  = 0

    for i in range(months_ahead):
        mn = today.month + i
        yr = today.year + (mn - 1) // 12
        mn = ((mn - 1) % 12) + 1
        forecast_date = date(yr, mn, 1)
        days          = monthrange(yr, mn)[1]

        # Build feature matrix: n_pairs × n_slots rows
        rows = []
        import math
        for pair in pairs:
            sid, lid = pair["station_id"], pair["line_id"]
            for weekday in WEEKDAYS:
                for hour in HOURS:
                    k   = (sid, lid, hour)
                    lag = meta["station_hour_avg"].get(k, 0)
                    tkt = meta["ticket_avg"].get(k, 0)
                    hour_sin  = round(math.sin(2 * math.pi * hour / 24), 6)
                    hour_cos  = round(math.cos(2 * math.pi * hour / 24), 6)
                    month_sin = round(math.sin(2 * math.pi * mn / 12), 6)
                    month_cos = round(math.cos(2 * math.pi * mn / 12), 6)
                    rows.append([sid, lid, hour, weekday, mn,
                                 int(weekday >= 5), lag, lag, tkt,
                                 hour_sin, hour_cos, month_sin, month_cos])

        X     = np.array(rows, dtype=float)
        preds = model.predict(X)                          # (n_pairs*n_slots, 2)

        pax_arr = np.maximum(preds[:, 0], 0).reshape(n_pairs, n_slots)
        occ_arr = np.maximum(preds[:, 1], 0).reshape(n_pairs, n_slots)

        avg_pax = pax_arr.mean(axis=1)
        avg_occ = np.minimum(occ_arr.mean(axis=1), 100)

        # Peak hour index (averaged across weekdays)
        occ_by_hour = occ_arr.reshape(n_pairs, len(WEEKDAYS), len(HOURS)).mean(axis=1)
        peak_idx    = np.argmax(occ_by_hour, axis=1)

        with engine.begin() as conn:
            for j, pair in enumerate(pairs):
                occ_val  = round(float(avg_occ[j]), 1)
                pax_val  = int(float(avg_pax[j]) * days * len(HOURS))
                peak_h   = HOURS[int(peak_idx[j])]

                if occ_val >= 95:   risk = "CRITICAL"
                elif occ_val >= 80: risk = "HIGH"
                elif occ_val >= 60: risk = "MEDIUM"
                else:               risk = "LOW"

                conn.execute(text("""
                    INSERT INTO monthly_forecasts
                        (forecast_month, line_id, station_id,
                         predicted_passengers, predicted_occupancy,
                         predicted_tickets, predicted_peak_hour,
                         suggested_action, created_at)
                    VALUES
                        (:month, :line_id, :station_id,
                         :pax, :occ, :tickets, :peak_hour, :action, :now)
                    ON CONFLICT (forecast_month, line_id, station_id)
                    DO UPDATE SET
                        predicted_passengers = EXCLUDED.predicted_passengers,
                        predicted_occupancy  = EXCLUDED.predicted_occupancy,
                        predicted_tickets    = EXCLUDED.predicted_tickets,
                        predicted_peak_hour  = EXCLUDED.predicted_peak_hour,
                        suggested_action     = EXCLUDED.suggested_action,
                        created_at           = EXCLUDED.created_at
                """), {
                    "month":      forecast_date,
                    "line_id":    pair["line_id"],
                    "station_id": pair["station_id"],
                    "pax":        pax_val,
                    "occ":        occ_val,
                    "tickets":    int(pax_val * 0.97),
                    "peak_hour":  peak_h,
                    "action":     RISK_ACTIONS[risk],
                    "now":        datetime.now(timezone.utc),
                })
                total_saved += 1

        logger.info(f"  {forecast_date.strftime('%B %Y')} — {n_pairs} pairs")

    logger.info(f"Complete. {total_saved} rows upserted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=6)
    args = parser.parse_args()
    run(args.months)
