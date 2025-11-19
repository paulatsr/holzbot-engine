from runner.steps.base import PipelineStep

TEMPLATE_EXPORTER = PipelineStep(
    name="Template Export",
    script="runner/detection/export_templates_from_detections.py",
    stage_key="detection_templates",
    description="Exportă fragmente pentru verificări manuale",
)
