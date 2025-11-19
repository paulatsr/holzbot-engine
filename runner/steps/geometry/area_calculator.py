from runner.steps.base import PipelineStep

AREA_CALCULATOR = PipelineStep(
    name="House Area",
    script="runner/geometry/house_area_from_plan.py",
    stage_key="geometry_area",
    description="Calculează aria fiecărui plan folosind Gemini",
)
