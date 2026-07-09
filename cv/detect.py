from ultralytics import YOLO


class Detector:
    """Wraps a YOLO model and exposes a single run() method for tracking."""

    def __init__(self, model_path: str):
      
        self.model = YOLO(model_path)

    def run(
        self,
        frame,
        tracker_config: str,
        imgsz: int = 640,
        conf: float | None = None,
        iou: float | None = None,
        persist: bool = True,
    ):
       
        kwargs = dict(
            classes=[0],       # person class only
            persist=persist,
            tracker=tracker_config,
            imgsz=imgsz,
            verbose=False,
        )
        # Only pass conf/iou when explicitly provided — avoids overriding Ultralytics defaults
        if conf is not None:
            kwargs["conf"] = conf
        if iou is not None:
            kwargs["iou"] = iou

        results = self.model.track(frame, **kwargs)
        return results
