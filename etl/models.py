"""
etl/models.py
-------------
SQLAlchemy ORM definitions for the three analytics tables.

These tables are written by the ETL pipeline and read by Power BI.
They are never written to by the CV pipeline.

Tables:
    hourly_station_statistics  — station busyness per hour
    line_statistics            — line-level daily KPIs
    bus_statistics             — per-bus daily KPIs
    etl_watermark              — tracks last successful ETL run
"""

from sqlalchemy import (
    Column, Integer, SmallInteger, Date, Numeric,
    String, DateTime, ForeignKey, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime, timezone


class AnalyticsBase(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# hourly_station_statistics
# How busy is each station every hour?
#
# Example row:
#   station: Bab Saadoun | hour: 08:00 | boardings: 245 | avg_occ: 76%
# ---------------------------------------------------------------------------

class HourlyStationStatistics(AnalyticsBase):
    __tablename__ = "hourly_station_statistics"
    __table_args__ = (
        UniqueConstraint("hour_start", "station_id", "line_id",
                         name="uq_hourly_station"),
        Index("ix_hss_hour_start", "hour_start"),
        Index("ix_hss_station_id", "station_id"),
        Index("ix_hss_line_id",    "line_id"),
    )

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    hour_start         = Column(DateTime(timezone=True), nullable=False)
    station_id         = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    line_id            = Column(Integer, ForeignKey("lines.line_id"),       nullable=True)
    total_boardings    = Column(Integer,      nullable=False, default=0)
    total_alightings   = Column(Integer,      nullable=False, default=0)
    avg_occupancy_rate = Column(Numeric(5,2), nullable=True)
    updated_at         = Column(DateTime(timezone=True), nullable=False,
                                default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return (
            f"<HourlyStation station={self.station_id} line={self.line_id} "
            f"hour={self.hour_start} IN={self.total_boardings} "
            f"avg_occ={self.avg_occupancy_rate}%>"
        )


# ---------------------------------------------------------------------------
# line_statistics
# Compare transport lines — daily summary.
#
# Example row:
#   line: 23 | passengers: 1523 | avg_occupancy: 81% | peak_hour: 8
# ---------------------------------------------------------------------------

class LineStatistics(AnalyticsBase):
    __tablename__ = "line_statistics"
    __table_args__ = (
        UniqueConstraint("date", "line_id", name="uq_line_statistics"),
        Index("ix_ls_date",    "date"),
        Index("ix_ls_line_id", "line_id"),
    )

    id                 = Column(Integer,      primary_key=True, autoincrement=True)
    date               = Column(Date,         nullable=False)
    line_id            = Column(Integer, ForeignKey("lines.line_id"), nullable=False)
    total_passengers   = Column(Integer,      nullable=False, default=0)
    avg_occupancy_rate = Column(Numeric(5,2), nullable=True)
    peak_hour          = Column(SmallInteger, nullable=True)   # 0–23
    updated_at         = Column(DateTime(timezone=True), nullable=False,
                                default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return (
            f"<LineStats line={self.line_id} date={self.date} "
            f"passengers={self.total_passengers} "
            f"avg_occ={self.avg_occupancy_rate}% peak={self.peak_hour}h>"
        )


# ---------------------------------------------------------------------------
# bus_statistics
# Monitor every bus — daily summary.
#
# Example row:
#   bus: 101 | passengers: 624 | max_occ: 96% | avg_occ: 68%
# ---------------------------------------------------------------------------

class BusStatistics(AnalyticsBase):
    __tablename__ = "bus_statistics"
    __table_args__ = (
        UniqueConstraint("date", "bus_id", name="uq_bus_statistics"),
        Index("ix_bs_date",   "date"),
        Index("ix_bs_bus_id", "bus_id"),
    )

    id                 = Column(Integer,      primary_key=True, autoincrement=True)
    date               = Column(Date,         nullable=False)
    bus_id             = Column(Integer, ForeignKey("buses.bus_id"), nullable=False)
    total_passengers   = Column(Integer,      nullable=False, default=0)
    max_occupancy_rate = Column(Numeric(5,2), nullable=True)
    avg_occupancy_rate = Column(Numeric(5,2), nullable=True)
    peak_hour          = Column(SmallInteger, nullable=True)   # 0–23
    updated_at         = Column(DateTime(timezone=True), nullable=False,
                                default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return (
            f"<BusStats bus={self.bus_id} date={self.date} "
            f"passengers={self.total_passengers} "
            f"max_occ={self.max_occupancy_rate}% "
            f"avg_occ={self.avg_occupancy_rate}%>"
        )


# ---------------------------------------------------------------------------
# etl_watermark
# Tracks the last successful ETL run per pipeline name.
# ---------------------------------------------------------------------------

class EtlWatermark(AnalyticsBase):
    __tablename__ = "etl_watermark"

    pipeline_name = Column(String(100), primary_key=True)
    last_run_at   = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return f"<EtlWatermark pipeline='{self.pipeline_name}' last_run={self.last_run_at}>"


# ---------------------------------------------------------------------------
# daily_system_statistics
# Executive Dashboard — one row per day, entire network.
#
# Example row:
#   date: 2026-07-06 | passengers: 2315 | avg_occ: 71% | peak: 08h | busiest: Line 23
# ---------------------------------------------------------------------------

class DailySystemStatistics(AnalyticsBase):
    __tablename__ = "daily_system_statistics"

    id                 = Column(Integer,      primary_key=True, autoincrement=True)
    date               = Column(Date,         nullable=False, unique=True)
    total_passengers   = Column(Integer,      nullable=False, default=0)
    avg_occupancy_rate = Column(Numeric(5,2), nullable=True)
    peak_hour          = Column(SmallInteger, nullable=True)   # 0–23
    busiest_line_id    = Column(Integer, ForeignKey("lines.line_id"), nullable=True)
    updated_at         = Column(DateTime(timezone=True), nullable=False,
                                default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return (
            f"<DailySystem date={self.date} "
            f"passengers={self.total_passengers} "
            f"avg_occ={self.avg_occupancy_rate}% "
            f"peak={self.peak_hour}h "
            f"busiest_line={self.busiest_line_id}>"
        )

# ---------------------------------------------------------------------------
# station_daily_statistics
# Daily rollup per station per line — busiest station analysis.
#
# Consistent dimensional design: date / station_id / line_id
#
# Example rows:
#   date: 2026-07-05 | station: Bab Saadoun | line: 23 | IN: 245 | OUT: 198 | avg: 76%
#   date: 2026-07-05 | station: Bab Saadoun | line: 42 | IN: 163 | OUT: 151 | avg: 64%
# ---------------------------------------------------------------------------

class StationDailyStatistics(AnalyticsBase):
    __tablename__ = "station_daily_statistics"
    __table_args__ = (
        UniqueConstraint("date", "station_id", "line_id",
                         name="uq_station_daily"),
        Index("ix_sds_date",       "date"),
        Index("ix_sds_station_id", "station_id"),
        Index("ix_sds_line_id",    "line_id"),
    )

    id                 = Column(Integer,      primary_key=True, autoincrement=True)
    date               = Column(Date,         nullable=False)
    station_id         = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    line_id            = Column(Integer, ForeignKey("lines.line_id"),       nullable=True)
    total_boardings    = Column(Integer,      nullable=False, default=0)
    total_alightings   = Column(Integer,      nullable=False, default=0)
    avg_occupancy_rate = Column(Numeric(5,2), nullable=True)
    peak_hour          = Column(SmallInteger, nullable=True)
    updated_at         = Column(DateTime(timezone=True), nullable=False,
                                default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return (
            f"<StationDaily date={self.date} "
            f"station={self.station_id} line={self.line_id} "
            f"IN={self.total_boardings} OUT={self.total_alightings} "
            f"avg_occ={self.avg_occupancy_rate}% peak={self.peak_hour}h>"
        )
