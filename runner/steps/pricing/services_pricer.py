from runner.steps.base import PipelineStep

ELECTRICITY_PRICER = PipelineStep(
    name="Electricity Pricing",
    script="runner/services/electricity_from_area.py",
    stage_key="pricing_electricity",
    description="Calculează costurile instalațiilor electrice",
)

HEATING_PRICER = PipelineStep(
    name="Heating Pricing",
    script="runner/services/heating_from_area.py",
    stage_key="pricing_heating",
    description="Calculează costurile pentru încălzire",
)

SEWAGE_PRICER = PipelineStep(
    name="Sewage Pricing",
    script="runner/services/sewage_from_area.py",
    stage_key="pricing_sewage",
    description="Calculează costurile sistemului de canalizare",
)
