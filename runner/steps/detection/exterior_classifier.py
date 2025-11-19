from runner.steps.base import PipelineStep

EXTERIOR_CLASSIFIER = PipelineStep(
    name="Exterior Doors",
    script="runner/segmentation/classify_exterior_doors.py",
    stage_key="detection_exterior",
    description="Clasifică ușile în interior/exterior",
)
