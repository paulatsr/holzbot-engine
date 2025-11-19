from runner.steps.base import PipelineStep

WALLS_ANALYZER = PipelineStep(
    name="Walls Analyzer",
    script="runner/geometry/walls_length_from_plan.py",
    stage_key="geometry_walls",
    description="Evaluează lungimile pereților interiori/exteriori",
)
