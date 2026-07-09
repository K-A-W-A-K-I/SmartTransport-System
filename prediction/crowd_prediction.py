"""
prediction/crowd_prediction.py
--------------------------------
Crowd prediction model for SmartTransport.

Trains on hourly_station_statistics (90 days of data) and predicts:
  - expected_passengers  (boardings in the next hour)
  - expected_occupancy   (% of bus capacity)
  - risk_level           (LOW / MEDIUM / HIGH / CRITICAL)

Models available:
  - LinearRegression   (fast baseline)
  - RandomForest       (default — best accuracy/speed trade-off)

Usage:
  # Train and save model
  python -m prediction.crowd_prediction --train

  # Predict for a specific context
  python -m prediction.crowd_prediction --predict \
      --station 3 --line 1 --hour 8 --weekday 0 --month 7

  # Evaluate model on held-out test set
  python -m prediction.crowd_prediction --evaluate
"""

import argparse
import logging
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.config import init_engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MODEL_DIR  = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)
MODEL_PATH = MODEL_DIR / "crowd_rf.pkl"
META_PATH  = MODEL_DIR / "crowd_meta.pkl"

# ---------------------------------------------------------------------------
# Risk thresholds (occupancy %)
# ---------------------------------------------------------------------------
RISK_THRESHOLDS = {
    "LOW":      (0,   60),
    "MEDIUM":   (60,  80),
    "HIGH":     (80,  95),
    "CRITICAL": (95, 200),
}


def occupancy_to_risk(occupancy_pct: float) -> str:
    for level, (low, high) in RISK_THRESHOLDS.items():
        if low <= occupancy_pct < high:
            return level
    return "CRITICAL"


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    "station_id",
    "line_id",
    "hour",
    "weekday",
    "month",
    "is_weekend",
    "lag_1h_boardings",     # boardings at same station 1 hour ago
    "lag_1w_boardings",     # boardings same hour last week
    "avg_tickets_hour",     # avg tickets sold this station/line/hour
]

TARGET_BOARDINGS  = "total_boardings"
TARGET_OCCUPANCY  = "avg_occupancy_rate"


def load_training_data() -> pd.DataFrame:
    """
    Load and join hourly_station_statistics with ticket_stats.
    Returns a DataFrame ready for feature engineering.
    """
    engine = init_engine()

    query = text("""
        SELECT
            h.hour_start,
            h.station_id,
            COALESCE(h.line_id, -1)          AS line_id,
            h.total_boardings,
            h.total_alightings,
            COALESCE(h.avg_occupancy_rate, 0) AS avg_occupancy_rate,
            h.hour,
            h.weekday,
            h.month,
            h.is_weekend,
            COALESCE(t.total_tickets_sold, 0) AS total_tickets_sold
        FROM hourly_station_statistics h
        LEFT JOIN ticket_stats t
            ON  t.date       = h.hour_start::date
            AND t.station_id = h.station_id
            AND COALESCE(t.line_id, -1) = COALESCE(h.line_id, -1)
        WHERE h.total_boardings IS NOT NULL
        ORDER BY h.station_id, h.line_id, h.hour_start
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    logger.info(f"Loaded {len(df):,} rows for training.")
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add lag features and ticket averages.
    Works on the full dataset sorted by (station_id, line_id, hour_start).
    """
    df = df.copy()
    df["hour_start"] = pd.to_datetime(df["hour_start"], utc=True)
    df = df.sort_values(["station_id", "line_id", "hour_start"]).reset_index(drop=True)

    # Lag 1h: previous hour boardings for same station+line
    df["lag_1h_boardings"] = (
        df.groupby(["station_id", "line_id"])["total_boardings"]
        .shift(1)
        .fillna(0)
    )

    # Lag 1 week (168 hours): same station+line+hour 7 days ago
    df["lag_1w_boardings"] = (
        df.groupby(["station_id", "line_id"])["total_boardings"]
        .shift(168)
        .fillna(0)
    )

    # Average tickets sold per (station, line, hour)
    ticket_avg = (
        df.groupby(["station_id", "line_id", "hour"])["total_tickets_sold"]
        .transform("mean")
        .fillna(0)
    )
    df["avg_tickets_hour"] = ticket_avg

    # is_weekend as int for sklearn
    df["is_weekend"] = df["is_weekend"].astype(int)

    return df


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(model_type: str = "random_forest") -> dict:
    """
    Train the prediction model and save it to disk.

    Args:
        model_type: 'linear' or 'random_forest'

    Returns:
        dict with train/test metrics
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    logger.info("Loading training data...")
    df = load_training_data()
    df = build_features(df)

    # Drop rows with NaN in features (first rows have no lag data)
    df = df.dropna(subset=FEATURE_COLS)
    logger.info(f"Training rows after dropping NaN: {len(df):,}")

    X = df[FEATURE_COLS].values
    y_boardings = df[TARGET_BOARDINGS].values
    y_occupancy = df[TARGET_OCCUPANCY].values

    # Stack targets
    Y = np.column_stack([y_boardings, y_occupancy])

    X_train, X_test, Y_train, Y_test = train_test_split(
        X, Y, test_size=0.2, random_state=42
    )

    logger.info(f"Train: {len(X_train):,} rows | Test: {len(X_test):,} rows")

    # Build model
    if model_type == "linear":
        base = LinearRegression()
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("reg",    MultiOutputRegressor(base)),
        ])
    else:  # random_forest (default)
        base = RandomForestRegressor(
            n_estimators=100,
            max_depth=12,
            min_samples_leaf=5,
            n_jobs=-1,
            random_state=42,
        )
        model = MultiOutputRegressor(base)

    logger.info(f"Training {model_type} model...")
    model.fit(X_train, Y_train)

    # Evaluate
    Y_pred = model.predict(X_test)

    mae_boardings = mean_absolute_error(Y_test[:, 0], Y_pred[:, 0])
    mae_occupancy = mean_absolute_error(Y_test[:, 1], Y_pred[:, 1])
    r2_boardings  = r2_score(Y_test[:, 0], Y_pred[:, 0])
    r2_occupancy  = r2_score(Y_test[:, 1], Y_pred[:, 1])

    metrics = {
        "model_type":      model_type,
        "train_rows":      len(X_train),
        "test_rows":       len(X_test),
        "mae_boardings":   round(mae_boardings, 2),
        "mae_occupancy":   round(mae_occupancy, 2),
        "r2_boardings":    round(r2_boardings, 3),
        "r2_occupancy":    round(r2_occupancy, 3),
    }

    logger.info("=" * 50)
    logger.info(f"  Model      : {model_type}")
    logger.info(f"  MAE passengers : {mae_boardings:.2f}")
    logger.info(f"  MAE occupancy  : {mae_occupancy:.2f}%")
    logger.info(f"  R² passengers  : {r2_boardings:.3f}")
    logger.info(f"  R² occupancy   : {r2_occupancy:.3f}")
    logger.info("=" * 50)

    # Save model + feature metadata
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    # Save feature averages for lag imputation at inference time
    meta = {
        "feature_cols": FEATURE_COLS,
        "station_hour_avg": (
            df.groupby(["station_id", "line_id", "hour"])["total_boardings"]
            .mean().to_dict()
        ),
        "ticket_avg": (
            df.groupby(["station_id", "line_id", "hour"])["total_tickets_sold"]
            .mean().to_dict()
        ),
    }
    with open(META_PATH, "wb") as f:
        pickle.dump(meta, f)

    logger.info(f"Model saved to {MODEL_PATH}")
    return metrics


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

class CrowdPredictor:
    """
    Loads the trained model and provides predictions.

    Example:
        predictor = CrowdPredictor()
        result = predictor.predict(station_id=3, line_id=1, hour=8, weekday=0, month=7)
        print(result)
        # {
        #   "expected_passengers": 43,
        #   "expected_occupancy":  82.4,
        #   "risk_level":          "HIGH"
        # }
    """

    def __init__(self):
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model not found at {MODEL_PATH}. "
                "Run: python -m prediction.crowd_prediction --train"
            )
        with open(MODEL_PATH, "rb") as f:
            self.model = pickle.load(f)
        with open(META_PATH, "rb") as f:
            self.meta = pickle.load(f)
        logger.info("CrowdPredictor loaded.")

    def predict(
        self,
        station_id: int,
        line_id: int,
        hour: int,
        weekday: int,
        month: int,
        lag_1h_boardings: float = None,
        lag_1w_boardings: float = None,
    ) -> dict:
        """
        Predict passengers and occupancy for a given context.

        Args:
            station_id:       Station to predict for
            line_id:          Line (use -1 for unknown)
            hour:             Hour of day (0–23)
            weekday:          0=Monday … 6=Sunday
            month:            1–12
            lag_1h_boardings: Actual boardings 1 hour ago (optional)
            lag_1w_boardings: Actual boardings same hour last week (optional)

        Returns:
            dict with expected_passengers, expected_occupancy, risk_level
        """
        is_weekend = int(weekday >= 5)

        # Impute lag features from historical averages if not provided
        key = (station_id, line_id, hour)
        if lag_1h_boardings is None:
            lag_1h_boardings = self.meta["station_hour_avg"].get(key, 0)
        if lag_1w_boardings is None:
            lag_1w_boardings = self.meta["station_hour_avg"].get(key, 0)

        avg_tickets = self.meta["ticket_avg"].get(key, 0)

        features = np.array([[
            station_id,
            line_id,
            hour,
            weekday,
            month,
            is_weekend,
            lag_1h_boardings,
            lag_1w_boardings,
            avg_tickets,
        ]])

        pred = self.model.predict(features)[0]
        expected_passengers = max(0, round(float(pred[0])))
        expected_occupancy  = max(0.0, min(200.0, round(float(pred[1]), 1)))
        risk_level          = occupancy_to_risk(expected_occupancy)

        return {
            "station_id":           station_id,
            "line_id":              line_id,
            "hour":                 hour,
            "weekday":              weekday,
            "month":                month,
            "expected_passengers":  expected_passengers,
            "expected_occupancy":   expected_occupancy,
            "risk_level":           risk_level,
        }

    def predict_next_hours(
        self,
        station_id: int,
        line_id: int,
        weekday: int,
        month: int,
        hours: int = 6,
        start_hour: int = None,
    ) -> list[dict]:
        """
        Predict for the next N hours starting from start_hour.
        Useful for generating a schedule view.
        """
        from datetime import datetime
        if start_hour is None:
            start_hour = datetime.now().hour

        results = []
        for i in range(hours):
            h = (start_hour + i) % 24
            result = self.predict(
                station_id=station_id,
                line_id=line_id,
                hour=h,
                weekday=weekday,
                month=month,
            )
            results.append(result)
        return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    parser = argparse.ArgumentParser(description="SmartTransport Crowd Prediction")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--train",    action="store_true", help="Train and save the model")
    group.add_argument("--predict",  action="store_true", help="Run a single prediction")
    group.add_argument("--evaluate", action="store_true", help="Print model evaluation metrics")
    group.add_argument("--forecast", action="store_true", help="Predict next 6 hours for a station")

    parser.add_argument("--model",   default="random_forest", choices=["linear", "random_forest"])
    parser.add_argument("--station", type=int, default=3,  help="station_id")
    parser.add_argument("--line",    type=int, default=1,  help="line_id")
    parser.add_argument("--hour",    type=int, default=8,  help="hour (0-23)")
    parser.add_argument("--weekday", type=int, default=0,  help="0=Mon … 6=Sun")
    parser.add_argument("--month",   type=int, default=7,  help="month (1-12)")
    parser.add_argument("--hours",   type=int, default=6,  help="hours to forecast")

    args = parser.parse_args()

    if args.train:
        train(model_type=args.model)

    elif args.predict:
        predictor = CrowdPredictor()
        result = predictor.predict(
            station_id=args.station,
            line_id=args.line,
            hour=args.hour,
            weekday=args.weekday,
            month=args.month,
        )
        print("\n── Prediction ──────────────────────────")
        print(f"  Station ID          : {result['station_id']}")
        print(f"  Line ID             : {result['line_id']}")
        print(f"  Hour                : {result['hour']:02d}:00")
        print(f"  Expected passengers : {result['expected_passengers']}")
        print(f"  Expected occupancy  : {result['expected_occupancy']}%")
        print(f"  Risk level          : {result['risk_level']}")
        print("────────────────────────────────────────\n")

    elif args.forecast:
        predictor = CrowdPredictor()
        results = predictor.predict_next_hours(
            station_id=args.station,
            line_id=args.line,
            weekday=args.weekday,
            month=args.month,
            hours=args.hours,
            start_hour=args.hour,
        )
        print(f"\n── {args.hours}h Forecast — Station {args.station} / Line {args.line} ──")
        print(f"  {'Hour':>5}  {'Passengers':>12}  {'Occupancy':>10}  {'Risk':>8}")
        print("  " + "-" * 45)
        for r in results:
            print(f"  {r['hour']:02d}:00  {r['expected_passengers']:>12}  {r['expected_occupancy']:>9}%  {r['risk_level']:>8}")
        print()

    elif args.evaluate:
        metrics = train(model_type=args.model)
        print("\n── Model Evaluation ────────────────────")
        for k, v in metrics.items():
            print(f"  {k:25}: {v}")
        print("────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
