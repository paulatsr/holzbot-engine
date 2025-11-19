from runner.steps.base import PipelineStep

HOUSE_SUMMARY = PipelineStep(
    name="House Summary",
    script="runner/pricing/house_price_summary.py",
    stage_key="pricing_summary",
    description="Agregă toate costurile într-un rezumat",
)
