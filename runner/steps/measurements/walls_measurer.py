from runner.steps.base import PipelineStep

WALLS_MEASURER = PipelineStep(
    name="Walls Area",
    script="runner/areas/walls_area_from_lenghts.py",
    stage_key="measure_walls",
    description="Calculează aria pereților din lungimi și înălțimi",
)
