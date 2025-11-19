from runner.steps.base import PipelineStep

OPENINGS_HYBRID = PipelineStep(
    name="Openings Hybrid",
    script="runner/detection/detect_openings_hybrid.py",
    stage_key="detection_openings",
    description="Combină șabloane + Gemini pentru uși/ferestre",
)
