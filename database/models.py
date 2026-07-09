"""
database/models.py
------------------
SQLAlchemy ORM model definitions — Milestone 2: Transport Master Data.

Master Data (relatively static):
    lines            — bus routes/lines
    drivers          — bus drivers
    buses            — physical vehicles (belongs to a line, assigned a driver)
    stations         — named stops along routes

Transactional Data (high-volume, append-only):
    sessions         — one row per YOLO counting pipeline run
    passenger_events — one row per individual passenger crossing
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Numeric,
    CheckConstraint, ForeignKey, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ===========================================================================
# MASTER DATA
# ===========================================================================

# ---------------------------------------------------------------------------
# lines
# ---------------------------------------------------------------------------

class Line(Base):
    __tablename__ = "lines"

    line_id     = Column(Integer, primary_key=True, autoincrement=True)
    line_name   = Column(String(100), nullable=False)
    line_number = Column(String(20),  nullable=False)

    buses = relationship("Bus", back_populates="line")

    def __repr__(self):
        return f"<Line id={self.line_id} number='{self.line_number}' name='{self.line_name}'>"


# ---------------------------------------------------------------------------
# drivers
# ---------------------------------------------------------------------------

class Driver(Base):
    __tablename__ = "drivers"

    driver_id      = Column(Integer, primary_key=True, autoincrement=True)
    name           = Column(String(255), nullable=False)
    license_number = Column(String(50),  nullable=False, unique=True)

    buses = relationship("Bus", back_populates="driver")

    def __repr__(self):
        return f"<Driver id={self.driver_id} name='{self.name}'>"


# ---------------------------------------------------------------------------
# buses
# ---------------------------------------------------------------------------

class Bus(Base):
    __tablename__ = "buses"

    bus_id        = Column(Integer, primary_key=True, autoincrement=True)
    capacity      = Column(Integer,     nullable=False)
    license_plate = Column(String(20),  nullable=True)
    line_id       = Column(Integer, ForeignKey("lines.line_id"),     nullable=True)
    driver_id     = Column(Integer, ForeignKey("drivers.driver_id"), nullable=True)

    # relationships
    line     = relationship("Line",   back_populates="buses")
    driver   = relationship("Driver", back_populates="buses")
    sessions = relationship("Session", back_populates="bus")
    events   = relationship("PassengerEvent", back_populates="bus",
                            foreign_keys="PassengerEvent.bus_id")

    def __repr__(self):
        return (
            f"<Bus id={self.bus_id} plate='{self.license_plate}' "
            f"capacity={self.capacity} line_id={self.line_id}>"
        )


# ---------------------------------------------------------------------------
# stations
# ---------------------------------------------------------------------------

class Station(Base):
    __tablename__ = "stations"

    station_id   = Column(Integer, primary_key=True, autoincrement=True)
    station_name = Column(String(255), nullable=False)

    events = relationship("PassengerEvent", back_populates="station")

    def __repr__(self):
        return f"<Station id={self.station_id} name='{self.station_name}'>"


# ===========================================================================
# TRANSACTIONAL DATA
# ===========================================================================

# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------

class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("entry_count >= 0", name="ck_sessions_entry_count"),
        CheckConstraint("exit_count  >= 0", name="ck_sessions_exit_count"),
        Index("ix_sessions_session_start", "session_start"),
        Index("ix_sessions_bus_id",        "bus_id"),
    )

    id            = Column(Integer, primary_key=True, autoincrement=True)
    bus_id        = Column(Integer, ForeignKey("buses.bus_id"), nullable=True)
    session_start = Column(DateTime(timezone=True), nullable=False)
    session_end   = Column(DateTime(timezone=True), nullable=False)
    mode          = Column(String(10),  nullable=False)
    video_file    = Column(String(255), nullable=False)
    entry_count   = Column(Integer, nullable=False, default=0)
    exit_count    = Column(Integer, nullable=False, default=0)
    processing_time_seconds = Column(Numeric(8, 2), nullable=True)

    # relationships
    bus    = relationship("Bus", back_populates="sessions")
    events = relationship(
        "PassengerEvent", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<Session id={self.id} bus_id={self.bus_id} mode='{self.mode}' "
            f"IN={self.entry_count} OUT={self.exit_count}>"
        )


# ---------------------------------------------------------------------------
# passenger_events
# ---------------------------------------------------------------------------

class PassengerEvent(Base):
    __tablename__ = "passenger_events"
    __table_args__ = (
        CheckConstraint("direction IN ('IN', 'OUT')",  name="ck_events_direction"),
        CheckConstraint("occupancy_after_event >= 0",  name="ck_events_occupancy"),
        CheckConstraint(
            "occupancy_rate IS NULL OR (occupancy_rate >= 0 AND occupancy_rate <= 200)",
            name="ck_events_occupancy_rate",
        ),
        Index("ix_events_timestamp",      "timestamp"),
        Index("ix_events_station_id",     "station_id"),
        Index("ix_events_bus_id",         "bus_id"),
        Index("ix_events_occupancy_rate", "occupancy_rate"),
    )

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    session_id            = Column(Integer, ForeignKey("sessions.id"),          nullable=False)
    bus_id                = Column(Integer, ForeignKey("buses.bus_id"),          nullable=True)
    station_id            = Column(Integer, ForeignKey("stations.station_id"),   nullable=True)
    timestamp             = Column(DateTime(timezone=True), nullable=False)
    direction             = Column(String(3),     nullable=False)   # 'IN' | 'OUT'
    occupancy_after_event = Column(Integer,       nullable=False, default=0)
    occupancy_rate        = Column(Numeric(5, 2), nullable=True)    # computed at insert time

    # relationships
    session = relationship("Session", back_populates="events")
    bus     = relationship("Bus",     back_populates="events",
                           foreign_keys=[bus_id])
    station = relationship("Station", back_populates="events")

    def __repr__(self):
        return (
            f"<PassengerEvent id={self.id} session={self.session_id} "
            f"bus={self.bus_id} dir={self.direction} "
            f"occ={self.occupancy_after_event} rate={self.occupancy_rate}%>"
        )
