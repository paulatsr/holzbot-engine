from runner.steps.base import PipelineStep

YOLO_DETECTOR = PipelineStep(
    name="YOLO Detector",
    script="runner/detection/import_yolo_detections.py",
    stage_key="detection_yolo",
    description="Importă detecțiile YOLO pentru uși/ferestre",
)
