from runner.steps.base import PipelineStep

OPENINGS_MEASURER = PipelineStep(
    name="Openings Adjustment",
    script="runner/areas/walls_area_with_openings.py",
    stage_key="measure_openings",
    description="Scade deschiderile din aria pereților",
)
