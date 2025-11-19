from runner.steps.base import PipelineStep

OPENINGS_PRICER = PipelineStep(
    name="Openings Pricing",
    script="runner/openings/openings_pricing.py",
    stage_key="pricing_openings",
    description="Calculează costurile pentru uși/ferestre",
)
