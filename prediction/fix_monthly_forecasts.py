"""
prediction/fix_monthly_forecasts.py
--------------------------------------
Regenerates monthly_forecasts using per-hour predictions from the ML model,
then picks the PEAK hour occupancy (not the average) as the representative
value for each line/station/month combination.

The current issue: averaging all hours (including quiet 22:00-05:00 hours)
pulls the occupancy down to 39-57% — always "Standard operations".

The fix: use the MAX predicted occupancy across all hours to represent
the monthly forecast, which reflects the actual risk the line faces.
This is the correct semantics: "What is the worst-case hour this month?"

Usage:
    python -m prediction.fix_monthly_forecasts
"""

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
logger = logging.getLogger("fix_monthly_forecasts")

MODEL_DIR  = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / "crowd_rf.pkl"
META_PATH  = MODEL_DIR / "crowd_meta.pkl"

RISK_ACTIONS = {
    "CRITICAL": "Deploy additional bus immediately",
    "HIGH":     "Pre-position standby bus",
    "MEDIUM":   "Monitor closely — alert drivers",
    "LOW":      "Standard operations",
}

PEAK_HOURS   = list(range(6, 23))   # 6am–10pm
WEEKDAYS_WD  = [0, 1, 2, 3]        # Mon–Thu (peak commuter days only)


def load_model():
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
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

    if not MODEL_PATH.exists():
        logger.error("Model not found. Run: python -m prediction.crowd_prediction --train")
        sys.exit(1)

    model, meta = load_model()
    engine      = init_engine()
    pairs       = get_lines_stations(engine)

    if not pairs:
        logger.error("No line_stations found.")
        return

    n_pairs     = len(pairs)
    n_slots     = len(WEEKDAYS_WD) * len(PEAK_HOURS)
    today       = date.today()
    total_saved = 0

    for i in range(months_ahead):
        mn = today.month + i
        yr = today.year + (mn - 1) // 12
        mn = ((mn - 1) % 12) + 1
        forecast_date = date(yr, mn, 1)
        days          = monthrange(yr, mn)[1]

        # Build feature matrix: peak weekdays × peak hours only
        rows = []
        for pair in pairs:
            sid, lid = pair["station_id"], pair["line_id"]
            for weekday in WEEKDAYS_WD:
                for hour in PEAK_HOURS:
                    k   = (sid, lid, hour)
                    lag = meta["station_hour_avg"].get(k, 0)
                    tkt = meta["ticket_avg"].get(k, 0)
                    rows.append([sid, lid, hour, weekday, mn,
                                 int(weekday >= 5), lag, lag, tkt])

        X     = np.array(rows, dtype=float)
        preds = model.predict(X)

        pax_arr = np.maximum(preds[:, 0], 0).reshape(n_pairs, n_slots)
        occ_arr = np.maximum(preds[:, 1], 0).reshape(n_pairs, n_slots)

        # Use MAX occupancy (peak scenario) instead of average
        peak_occ = np.minimum(occ_arr.max(axis=1), 100)
        avg_pax  = pax_arr.mean(axis=1)

        # Peak hour: which hour has highest occupancy on average across weekdays
        occ_by_hour = occ_arr.reshape(n_pairs, len(WEEKDAYS_WD), len(PEAK_HOURS)).mean(axis=1)
        peak_idx    = np.argmax(occ_by_hour, axis=1)

        with engine.begin() as conn:
            for j, pair in enumerate(pairs):
                occ_val  = round(float(peak_occ[j]), 1)
                pax_val  = int(float(avg_pax[j]) * days * len(PEAK_HOURS))
                peak_h   = PEAK_HOURS[int(peak_idx[j])]

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

        logger.info(f"  {forecast_date.strftime('%B %Y')} — {n_pairs} pairs | "
                    f"occ range: {peak_occ.min():.1f}% – {peak_occ.max():.1f}%")

    logger.info(f"Done. {total_saved} rows updated in monthly_forecasts.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=6)
    args = parser.parse_args()
    run(args.months)
