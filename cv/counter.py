import logging
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)


class LineCounter:

    def __init__(
        self,
        door_x_start: int,
        door_x_end: int,
        mode: str,
        line_y: int = 0,
        line_y_left: int = 0,
        line_y_right: int = 0,
        on_crossing: Callable[[str, int, datetime], None] | None = None,
    ):
        if mode not in ("color", "bw"):
            raise ValueError(f"Invalid mode '{mode}'. Must be 'color' or 'bw'.")

        self.mode = mode
        self.door_x_start = door_x_start
        self.door_x_end = door_x_end
        self.line_y = line_y
        self.line_y_left = line_y_left
        self.line_y_right = line_y_right
        self._on_crossing = on_crossing

        self._entry_count: int = 0
        self._exit_count: int = 0
        self._track_memory: dict[int, float] = {}
        self._crossed_ids: dict[int, int] = {}
        self._recent_crossings: list[tuple[int, float, float]] = []

    # ------------------------------------------------------------------
    # Public read-only properties
    # ------------------------------------------------------------------

    @property
    def entry_count(self) -> int:
        return self._entry_count

    @property
    def exit_count(self) -> int:
        return self._exit_count

    # ------------------------------------------------------------------
    # Public update interface
    # ------------------------------------------------------------------

    def update(
        self,
        track_id: int,
        center_x: float,
        center_y: float,
        frame_number: int,
        box_width: float = 0.0,
        box_height: float = 0.0,
    ) -> None:
        """
        Process one detection for the given frame.

        Args:
            track_id:     Unique tracker ID for this person.
            center_x:     Horizontal center of the bounding box (pixels).
            center_y:     Vertical center of the bounding box (pixels).
            frame_number: Current frame index (used for debounce timing).
            box_width:    Bounding box width  (required in bw mode).
            box_height:   Bounding box height (required in bw mode).
        """
        if self.mode == "color":
            self._update_color(track_id, center_x, center_y, frame_number)
        else:
            self._update_bw(track_id, center_x, center_y, box_width, box_height, frame_number)

    # ------------------------------------------------------------------
    # Color pipeline logic
    # ------------------------------------------------------------------

    def _update_color(
        self,
        track_id: int,
        center_x: float,
        center_y: float,
        frame_number: int,
    ) -> None:
        if center_x < self.door_x_start or center_x > self.door_x_end:
            return

        tracking_y = center_y

        if track_id not in self._track_memory:
            self._track_memory[track_id] = tracking_y
            return

        last_y = self._track_memory[track_id]

        # Debounce: 90-frame cooldown per ID (~3 s at 30 fps)
        if track_id in self._crossed_ids:
            if (frame_number - self._crossed_ids[track_id]) < 90:
                self._track_memory[track_id] = tracking_y
                return

        if last_y < self.line_y and tracking_y >= self.line_y:
            self._entry_count += 1
            self._crossed_ids[track_id] = frame_number
            self._fire_crossing("IN")
            logger.debug(f"ID {track_id} crossed downward (ENTRY) at y={tracking_y:.1f}")
        elif last_y >= self.line_y and tracking_y < self.line_y:
            self._exit_count += 1
            self._crossed_ids[track_id] = frame_number
            self._fire_crossing("OUT")
            logger.debug(f"ID {track_id} crossed upward (EXIT) at y={tracking_y:.1f}")

        self._track_memory[track_id] = tracking_y

    # ------------------------------------------------------------------
    # BW pipeline logic
    # ------------------------------------------------------------------

    def _update_bw(
        self,
        track_id: int,
        center_x: float,
        center_y: float,
        box_width: float,
        box_height: float,
        frame_number: int,
    ) -> None:
        # Filter out small detections — likely objects, not people
        if box_width < 30 or box_height < 50:
            return

        # Adjusted tracking position: 75% down the bounding box
        tracking_y = center_y + (box_height * 0.25)

        if center_x < self.door_x_start or center_x > self.door_x_end:
            return

        # Inclined line Y at this x via linear interpolation
        line_y_at_x = (
            self.line_y_left
            + (self.line_y_right - self.line_y_left)
            * (center_x - self.door_x_start)
            / (self.door_x_end - self.door_x_start)
        )

        if track_id not in self._track_memory:
            self._track_memory[track_id] = tracking_y
            logger.debug(f"ID {track_id} first seen at tracking_y={tracking_y:.1f}, line_y={line_y_at_x:.1f}")
            return

        last_y = self._track_memory[track_id]

        # Debounce: 120-frame cooldown per ID (~4 s at 30 fps)
        if track_id in self._crossed_ids:
            if (frame_number - self._crossed_ids[track_id]) < 120:
                self._track_memory[track_id] = tracking_y
                return

        if last_y < line_y_at_x and tracking_y >= line_y_at_x:
            if not self._is_duplicate_crossing(frame_number, center_x, tracking_y, track_id, "ENTRY"):
                self._entry_count += 1
                self._crossed_ids[track_id] = frame_number
                self._record_crossing(frame_number, center_x, tracking_y)
                self._fire_crossing("IN")
                logger.debug(
                    f"ID {track_id} ENTRY — tracking_y: {last_y:.1f} → {tracking_y:.1f}, "
                    f"line: {line_y_at_x:.1f}"
                )

        elif last_y >= line_y_at_x and tracking_y < line_y_at_x:
            if not self._is_duplicate_crossing(frame_number, center_x, tracking_y, track_id, "EXIT"):
                self._exit_count += 1
                self._crossed_ids[track_id] = frame_number
                self._record_crossing(frame_number, center_x, tracking_y)
                self._fire_crossing("OUT")
                logger.debug(
                    f"ID {track_id} EXIT — tracking_y: {last_y:.1f} → {tracking_y:.1f}, "
                    f"line: {line_y_at_x:.1f}"
                )

        self._track_memory[track_id] = tracking_y

    def _is_duplicate_crossing(
        self,
        frame_number: int,
        center_x: float,
        tracking_y: float,
        track_id: int,
        direction: str,
    ) -> bool:
        """Return True if this crossing is suspiciously close to a recent one."""
        self._recent_crossings = [
            (f, x, y)
            for (f, x, y) in self._recent_crossings
            if (frame_number - f) < 60
        ]
        for (recent_frame, recent_x, recent_y) in self._recent_crossings:
            if (frame_number - recent_frame) < 45:
                distance = ((center_x - recent_x) ** 2 + (tracking_y - recent_y) ** 2) ** 0.5
                if distance < 25:
                    logger.debug(
                        f"ID {track_id} {direction} ignored — duplicate within {distance:.0f}px"
                    )
                    return True
        return False

    def _record_crossing(self, frame_number: int, center_x: float, tracking_y: float) -> None:
        """Append a crossing to the recent-crossings list."""
        self._recent_crossings.append((frame_number, center_x, tracking_y))

    def _fire_crossing(self, direction: str) -> None:
        """Compute current occupancy and invoke the on_crossing callback if set."""
        if self._on_crossing is None:
            return
        occupancy = self._entry_count - self._exit_count
        try:
            self._on_crossing(direction, occupancy, datetime.now(timezone.utc))
        except Exception as e:
            logger.error(f"on_crossing callback error: {e}")
