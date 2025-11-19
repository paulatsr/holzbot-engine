from runner.steps.base import PipelineStep

SCALE_DETECTOR = PipelineStep(
    name="Scale Detector",
    script="runner/geometry/scale_from_plan.py",
    stage_key="geometry_scale",
    description="Estimează scara fiecărui plan (m/pixel)",
)
