import sys; sys.path.insert(0, '.')
from database.config import init_engine
from sqlalchemy import text
e = init_engine()
tables = ['passenger_events', 'sessions', 'ticket_sales',
          'hourly_station_statistics', 'daily_system_statistics',
          'recommendations', 'monthly_forecasts']
with e.connect() as c:
    for t in tables:
        n = c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        print(f"  {t:<35} {n:>10,} rows")
