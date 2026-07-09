"""
database/session_service.py
---------------------------
Business logic layer between main.py and the database.

Lifecycle:
  start()       → verifies DB, caches bus capacity, inserts placeholder session row
  on_crossing() → inserts PassengerEvent with occupancy_rate
  end()         → updates session row with final counts, end time, processing duration
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from database.db_client import insert_session, update_session, insert_event, get_bus_capacity
from database.config import verify_connection

logger = logging.getLogger("smarttransport.session_service")


class SessionService:
    """
    Manages the lifecycle of one counting session.

    Usage in main.py:
        svc = SessionService(mode="color", video_file="busfinal.mp4", bus_id=1)
        svc.start()
        counter = LineCounter(..., on_crossing=svc.on_crossing)
        svc.end(entry_count, exit_count, processing_time_seconds)
    """

    def __init__(self, mode: str, video_file: str, bus_id: int | None = None, station_id: int | None = None):
        self.mode       = mode
        self.video_file = video_file
        self.bus_id     = bus_id
        self.station_id = station_id  # station where the bus is currently stopped

        self._session_id:    int | None      = None
        self._session_start: datetime | None = None
        self._db_available:  bool            = True
        self._bus_capacity:  int | None      = None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not verify_connection():
            logger.warning("DB unreachable — running without persistence.")
            self._db_available = False
            return

        # Cache bus capacity once — used for every occupancy_rate calculation
        if self.bus_id is not None:
            self._bus_capacity = get_bus_capacity(self.bus_id)
            if self._bus_capacity is None:
                logger.warning(f"Bus id={self.bus_id} not found — occupancy_rate will be NULL.")

        self._session_start = datetime.now(timezone.utc)

        session_id = insert_session({
            "session_start": self._session_start,
            "session_end":   self._session_start,
            "mode":          self.mode,
            "video_file":    self.video_file,
            "bus_id":        self.bus_id,
            "entry_count":   0,
            "exit_count":    0,
        })

        if session_id is not None:
            self._session_id = session_id
            cap = str(self._bus_capacity) if self._bus_capacity else "unknown"
            logger.info(
                f"Session started — id={session_id} | bus_id={self.bus_id} | "
                f"station_id={self.station_id} | capacity={cap}"
            )
        else:
            logger.error("Failed to insert session row — running without persistence.")
            self._db_available = False

    def end(self, entry_count: int, exit_count: int,
            processing_time_seconds: float | None = None) -> int | None:
        logger.info(f"Session complete — IN: {entry_count} | OUT: {exit_count}")

        if not self._db_available or self._session_id is None:
            logger.warning("DB unavailable — session totals not persisted.")
            return None

        updates = {
            "session_end": datetime.now(timezone.utc),
            "entry_count": entry_count,
            "exit_count":  exit_count,
        }
        if processing_time_seconds is not None:
            updates["processing_time_seconds"] = processing_time_seconds

        success = update_session(self._session_id, updates)

        if success:
            pt = f"{processing_time_seconds:.1f}s" if processing_time_seconds else "n/a"
            logger.info(
                f"Session saved — id={self._session_id} | "
                f"IN={entry_count} | OUT={exit_count} | duration={pt}"
            )
        else:
            logger.error(f"Failed to update session id={self._session_id}.")

        return self._session_id

    # ------------------------------------------------------------------
    # Crossing callback — passed directly to LineCounter
    # ------------------------------------------------------------------

    def on_crossing(self, direction: str, occupancy: int, timestamp: datetime) -> None:
        if not self._db_available or self._session_id is None:
            return

        occ = max(occupancy, 0)

        if self._bus_capacity and self._bus_capacity > 0:
            rate = round(Decimal(occ) / Decimal(self._bus_capacity) * 100, 2)
        else:
            rate = None

        insert_event({
            "session_id":            self._session_id,
            "bus_id":                self.bus_id,
            "station_id":            self.station_id,
            "timestamp":             timestamp,
            "direction":             direction,
            "occupancy_after_event": occ,
            "occupancy_rate":        rate,
        })

        logger.debug(
            f"Event — {direction} | occupancy={occ} | rate={rate}% | session={self._session_id}"
        )
