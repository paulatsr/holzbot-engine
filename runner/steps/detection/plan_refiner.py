from runner.steps.base import PipelineStep

PLAN_REFINER = PipelineStep(
    name="Plan Refiner",
    script="runner/segmentation/plan_segmentation.py",
    stage_key="segmentation",
    description="Segmentare și rafinare plan pentru camere",
)
