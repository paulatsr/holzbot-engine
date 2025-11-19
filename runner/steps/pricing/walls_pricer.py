from runner.steps.base import PipelineStep

WALLS_PRICER = PipelineStep(
    name="Walls Pricing",
    script="runner/areas/walls_area_with_openings.py",
    stage_key="pricing_walls",
    description="Aplică ajustările pentru pereți nete",
)
