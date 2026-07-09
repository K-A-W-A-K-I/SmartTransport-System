"""
main.py
-------
Entry point for the SmartTransport passenger counter.

Usage:
    python main.py --mode color --bus-id 1 --station-id 3
    python main.py --mode bw   --bus-id 2 --station-id 4
    python main.py --mode color          # uses defaults from .env and mode defaults
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import cv2
from dotenv import load_dotenv

from cv.detect import Detector
from cv.counter import LineCounter
from cv.tracker import get_tracker_config
from database.session_service import SessionService

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("smarttransport.main")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "videos"
MODEL_PATH = str(BASE_DIR / "yolo11n.pt")

load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="SmartTransport Passenger Counter")
    parser.add_argument(
        "--mode",
        choices=["color", "bw"],
        required=False,
        help="Camera mode: 'color' for color camera, 'bw' for overhead B&W camera.",
    )
    parser.add_argument(
        "--bus-id",
        type=int,
        default=None,
        help="Bus ID to associate with this session (overrides BUS_ID in .env).",
    )
    parser.add_argument(
        "--station-id",
        type=int,
        default=None,
        help="Station ID where this bus is currently stopped (overrides mode default).",
    )
    args = parser.parse_args()

    if args.mode is None:
        parser.print_help()
        logger.error("--mode is required. Use --mode color or --mode bw.")
        sys.exit(2)

    # Resolve bus_id: CLI arg > .env > None
    if args.bus_id is None:
        env_bus_id = os.getenv("BUS_ID")
        args.bus_id = int(env_bus_id) if env_bus_id else None

    # Resolve station_id: CLI arg > mode default
    # color (busfinal.mp4) → Bab Saadoun (station_id=3) on Line 23
    # bw    (bus.mp4)      → Ariana Centre (station_id=4) on Line 42
    if args.station_id is None:
        args.station_id = 3 if args.mode == "color" else 4

    return args


# ---------------------------------------------------------------------------
# Pipeline configuration per mode
# ---------------------------------------------------------------------------

def build_pipeline_config(mode: str, width: int, frame_height: int, on_crossing=None) -> dict:
    """Return mode-specific geometry and tracker settings."""
    if mode == "color":
        return dict(
            video_file="busfinal.mp4",
            tracker_name="botsort",
            conf=None,
            iou=None,
            counter=LineCounter(
                mode="color",
                line_y=int(frame_height * 0.55),
                door_x_start=int(width * 0.20),
                door_x_end=int(width * 0.65),
                on_crossing=on_crossing,
            ),
        )
    else:  # bw
        return dict(
            video_file="bus.mp4",
            tracker_name="bytetrack_bw",
            conf=0.20,
            iou=0.3,
            counter=LineCounter(
                mode="bw",
                line_y_left=int(frame_height * 0.32),
                line_y_right=int(frame_height * 0.52),
                door_x_start=int(width * 0.60),
                door_x_end=int(width * 0.98),
                on_crossing=on_crossing,
            ),
        )


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def draw_counting_line(frame, mode: str, config: dict) -> None:
    counter: LineCounter = config["counter"]
    if mode == "color":
        cv2.line(
            frame,
            (counter.door_x_start, counter.line_y),
            (counter.door_x_end, counter.line_y),
            (0, 0, 255),
            2,
        )
    else:
        cv2.line(
            frame,
            (counter.door_x_start, counter.line_y_left),
            (counter.door_x_end, counter.line_y_right),
            (0, 0, 255),
            2,
        )


def draw_overlays(frame, avg_fps: float, entry_count: int, exit_count: int) -> None:
    cv2.putText(frame, f"FPS: {avg_fps:.1f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.putText(frame, f"IN:  {entry_count}", (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.putText(frame, f"OUT: {exit_count}", (10, 110),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(mode: str, bus_id: int | None, station_id: int | None) -> None:
    video_file_map = {"color": "busfinal.mp4", "bw": "bus.mp4"}
    video_path = DATA_DIR / video_file_map[mode]

    video = cv2.VideoCapture(str(video_path))
    if not video.isOpened():
        logger.error(f"Could not open video file: {video_path}")
        sys.exit(1)

    fps          = video.get(cv2.CAP_PROP_FPS)
    width        = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    logger.info(f"Video: {video_path.name} | FPS: {fps} | Resolution: {width}x{frame_height}")

    # --- Database session service ---
    svc = SessionService(mode=mode, video_file=video_file_map[mode], bus_id=bus_id, station_id=station_id)
    svc.start()

    config         = build_pipeline_config(mode, width, frame_height, on_crossing=svc.on_crossing)
    counter        = config["counter"]
    tracker_config = get_tracker_config(config["tracker_name"])
    detector       = Detector(MODEL_PATH)

    logger.info(f"Mode: {mode} | Tracker: {config['tracker_name']} | Bus ID: {bus_id} | Station ID: {station_id}")
    logger.info("Press 'q' to quit.")

    frame_times: list[float] = []
    pipeline_start = time.time()

    while True:
        success, frame = video.read()
        if not success:
            break

        frame_number = int(video.get(cv2.CAP_PROP_POS_FRAMES))

        t0      = time.time()
        results = detector.run(
            frame,
            tracker_config=tracker_config,
            conf=config["conf"],
            iou=config["iou"],
        )
        elapsed = time.time() - t0

        frame_times.append(elapsed)
        if len(frame_times) > 30:
            frame_times.pop(0)
        avg_fps = 1.0 / (sum(frame_times) / len(frame_times))

        if results[0].boxes.id is not None:
            ids        = results[0].boxes.id.int().tolist()
            boxes_xywh = results[0].boxes.xywh.tolist()

            if mode == "color":
                for track_id, box in zip(ids, boxes_xywh):
                    counter.update(
                        track_id=track_id,
                        center_x=box[0],
                        center_y=box[1],
                        frame_number=frame_number,
                    )
            else:
                for track_id, box in zip(ids, boxes_xywh):
                    counter.update(
                        track_id=track_id,
                        center_x=box[0],
                        center_y=box[1],
                        frame_number=frame_number,
                        box_width=box[2],
                        box_height=box[3],
                    )

            logger.debug(f"Inference: {elapsed*1000:.1f}ms | Avg FPS: {avg_fps:.1f} | IDs: {ids}")
        else:
            logger.debug(f"Inference: {elapsed*1000:.1f}ms | Avg FPS: {avg_fps:.1f} | No IDs")

        annotated_frame = results[0].plot()
        draw_counting_line(annotated_frame, mode, config)
        draw_overlays(annotated_frame, avg_fps, counter.entry_count, counter.exit_count)

        cv2.imshow("SmartTransport Passenger Counter", annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    processing_time = round(time.time() - pipeline_start, 2)
    video.release()
    cv2.destroyAllWindows()
    svc.end(counter.entry_count, counter.exit_count, processing_time)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = parse_args()
    run(args.mode, args.bus_id, args.station_id)
