"""Reset watermark so ETL processes all historical data from 2025."""
import sys; sys.path.insert(0, '.')
from database.config import init_engine
from sqlalchemy import text

engine = init_engine()
with engine.begin() as conn:
    conn.execute(text("DELETE FROM etl_watermark WHERE pipeline_name = 'main'"))
    print("Watermark cleared. Running full ETL...")

import subprocess
result = subprocess.run(
    [sys.executable, "-m", "etl.run_etl"],
    cwd="c:\\Users\\boule\\Desktop\\SmartTransport"
)
print("ETL exit code:", result.returncode)
