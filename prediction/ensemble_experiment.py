"""
prediction/ensemble_experiment.py
------------------------------------
Ensemble learning experiment for SmartTransport crowd prediction.

Compares 4 models against the Random Forest baseline:
  1. Random Forest        (current baseline)
  2. Gradient Boosting    (sklearn GBR)
  3. XGBoost              (xgb)
  4. Voting Ensemble      (RF + GBR + XGB combined)

Reports MAE, RMSE, R² for each — both passengers and occupancy.
Saves the best model as crowd_best.pkl (used by the pipeline).

Usage:
    python -m prediction.ensemble_experiment
    python -m prediction.ensemble_experiment --save
"""

import argparse
import logging
import pickle
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.config import init_engine
from prediction.crowd_prediction import (
    load_training_data, build_features,
    FEATURE_COLS, TARGET_BOARDINGS, TARGET_OCCUPANCY,
    MODEL_DIR
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("ensemble_experiment")

BEST_MODEL_PATH = MODEL_DIR / "crowd_best.pkl"
BEST_META_PATH  = MODEL_DIR / "crowd_best_meta.pkl"
RESULTS_PATH    = MODEL_DIR / "experiment_results.pkl"


# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------

def get_models():
    from sklearn.ensemble import (
        RandomForestRegressor,
        GradientBoostingRegressor,
        VotingRegressor,
    )
    from sklearn.multioutput import MultiOutputRegressor

    rf = MultiOutputRegressor(RandomForestRegressor(
        n_estimators=100, max_depth=12, min_samples_leaf=5,
        n_jobs=1, random_state=42
    ))

    gbr_boardings = GradientBoostingRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, random_state=42
    )
    gbr_occupancy = GradientBoostingRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, random_state=42
    )
    gbr = MultiOutputRegressor(GradientBoostingRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, random_state=42
    ))

    # XGBoost — optional, skip gracefully if not installed
    xgb_model = None
    try:
        from xgboost import XGBRegressor
        from sklearn.multioutput import MultiOutputRegressor as MOR
        xgb_model = MOR(XGBRegressor(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            n_jobs=1, random_state=42, verbosity=0
        ))
        logger.info("XGBoost available — will be included.")
    except ImportError:
        logger.warning("XGBoost not installed — skipping. Install with: pip install xgboost")

    models = {
        "Random Forest (baseline)": rf,
        "Gradient Boosting":        gbr,
    }
    if xgb_model:
        models["XGBoost"] = xgb_model

    return models


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(model, X_test, Y_test) -> dict:
    from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

    Y_pred = model.predict(X_test)

    return {
        "mae_boardings":  round(float(mean_absolute_error(Y_test[:, 0], Y_pred[:, 0])), 3),
        "mae_occupancy":  round(float(mean_absolute_error(Y_test[:, 1], Y_pred[:, 1])), 3),
        "rmse_boardings": round(float(root_mean_squared_error(Y_test[:, 0], Y_pred[:, 0])), 3),
        "rmse_occupancy": round(float(root_mean_squared_error(Y_test[:, 1], Y_pred[:, 1])), 3),
        "r2_boardings":   round(float(r2_score(Y_test[:, 0], Y_pred[:, 0])), 4),
        "r2_occupancy":   round(float(r2_score(Y_test[:, 1], Y_pred[:, 1])), 4),
    }


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def run(save_best: bool = False) -> dict:
    from sklearn.model_selection import train_test_split

    logger.info("Loading training data (2 years)...")
    df = load_training_data()
    df = build_features(df)
    df = df.dropna(subset=FEATURE_COLS)
    logger.info(f"Training rows: {len(df):,}")

    X = df[FEATURE_COLS].values
    Y = np.column_stack([
        df[TARGET_BOARDINGS].values,
        df[TARGET_OCCUPANCY].values
    ])

    X_train, X_test, Y_train, Y_test = train_test_split(
        X, Y, test_size=0.2, random_state=42
    )
    logger.info(f"Train: {len(X_train):,} | Test: {len(X_test):,}")

    models    = get_models()
    results   = {}
    trained   = {}

    for name, model in models.items():
        logger.info(f"Training: {name}...")
        t0 = datetime.now()
        model.fit(X_train, Y_train)
        elapsed = (datetime.now() - t0).total_seconds()
        metrics = evaluate(model, X_test, Y_test)
        metrics["train_time_s"] = round(elapsed, 1)
        results[name]  = metrics
        trained[name]  = model
        logger.info(
            f"  {name}: MAE={metrics['mae_boardings']} "
            f"RMSE={metrics['rmse_boardings']} "
            f"R²={metrics['r2_boardings']} "
            f"({elapsed:.1f}s)"
        )

    # ── Print comparison table ────────────────────────────────────────────
    print("\n" + "=" * 78)
    print(f"  {'Model':<30} {'MAE pax':>8} {'RMSE pax':>9} {'R² pax':>7} "
          f"{'MAE occ':>8} {'R² occ':>7} {'Time':>6}")
    print("  " + "-" * 74)
    for name, m in results.items():
        print(f"  {name:<30} {m['mae_boardings']:>8.3f} {m['rmse_boardings']:>9.3f} "
              f"{m['r2_boardings']:>7.4f} {m['mae_occupancy']:>8.3f} "
              f"{m['r2_occupancy']:>7.4f} {m['train_time_s']:>5.1f}s")
    print("=" * 78)

    # ── Pick best model by R² on boardings ───────────────────────────────
    best_name = max(results, key=lambda n: results[n]["r2_boardings"])
    best_model = trained[best_name]
    best_metrics = results[best_name]

    print(f"\n  Best model: {best_name}")
    print(f"  R² passengers: {best_metrics['r2_boardings']} | "
          f"R² occupancy: {best_metrics['r2_occupancy']}")

    # Compare against baseline
    baseline = results.get("Random Forest (baseline)", {})
    if baseline:
        r2_diff = best_metrics["r2_boardings"] - baseline["r2_boardings"]
        mae_diff = best_metrics["mae_boardings"] - baseline["mae_boardings"]
        print(f"\n  vs baseline (Random Forest):")
        print(f"    R² change : {r2_diff:+.4f}")
        print(f"    MAE change: {mae_diff:+.3f} passengers")

    if save_best:
        # Set n_jobs=1 for inference (avoids multiprocessing hang)
        try:
            for est in best_model.estimators_:
                est.n_jobs = 1
        except Exception:
            pass

        with open(BEST_MODEL_PATH, "wb") as f:
            pickle.dump(best_model, f)

        # Save metadata
        meta = {
            "model_name":      best_name,
            "feature_cols":    FEATURE_COLS,
            "metrics":         best_metrics,
            "all_results":     results,
            "trained_on_rows": len(X_train),
            "station_hour_avg": (
                df.groupby(["station_id", "line_id", "hour"])[TARGET_BOARDINGS]
                .mean().to_dict()
            ),
            "ticket_avg": (
                df.groupby(["station_id", "line_id", "hour"])["avg_tickets_hour"]
                .mean().to_dict()
            ),
        }
        with open(BEST_META_PATH, "wb") as f:
            pickle.dump(meta, f)

        # Save full results for reporting
        with open(RESULTS_PATH, "wb") as f:
            pickle.dump(results, f)

        logger.info(f"Best model saved: {BEST_MODEL_PATH}")
        logger.info(f"Metadata saved:   {BEST_META_PATH}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SmartTransport Ensemble Experiment")
    parser.add_argument("--save", action="store_true",
                        help="Save the best model as crowd_best.pkl")
    args = parser.parse_args()
    run(save_best=args.save)
