"""
webapp/routes/settings.py
"""
import os
from pathlib import Path
from flask import Blueprint, render_template
from sqlalchemy import text

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/")
def index():
    from database.config import init_engine
    db_ok = False
    db_version = "Unknown"
    try:
        engine = init_engine()
        with engine.connect() as conn:
            db_version = conn.execute(text("SELECT version()")).scalar()
            db_ok = True
    except Exception:
        pass

    root = Path(__file__).parent.parent.parent
    yolo_path = root / "yolo11n.pt"
    yolo_exists = yolo_path.exists()
    yolo_size = f"{yolo_path.stat().st_size / 1024 / 1024:.1f} MB" if yolo_exists else "Not found"

    ml_path = root / "prediction" / "models" / "crowd_rf.pkl"
    ml_exists = ml_path.exists()

    return render_template("settings.html",
        db_ok=db_ok,
        db_version=(db_version[:70] + "…") if db_version and len(db_version) > 70 else db_version,
        db_name=os.getenv("DB_NAME", "smart_transport"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=os.getenv("DB_PORT", "5432"),
        yolo_exists=yolo_exists,
        yolo_size=yolo_size,
        ml_exists=ml_exists,
        version="1.0.0",
    )
