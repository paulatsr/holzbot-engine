from runner.steps.base import PipelineStep

ROOF_PRICER = PipelineStep(
    name="Roof Pricing",
    script="runner/roof/roof_price_from_area.py",
    stage_key="pricing_roof",
    description="Estimează costurile acoperișului",
)
