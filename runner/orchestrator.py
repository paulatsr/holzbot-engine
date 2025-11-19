from __future__ import annotations

from pathlib import Path
from typing import Iterable

from runner.aggregator import pdf_generator, plans_merger
from runner.config.settings import RunnerSettings
from runner.segmenter.detector import detect_plans
from runner.steps.base import PipelineStep
from runner.steps.detection.exterior_classifier import EXTERIOR_CLASSIFIER
from runner.steps.detection.openings_hybrid import OPENINGS_HYBRID
from runner.steps.detection.plan_refiner import PLAN_REFINER
from runner.steps.detection.yolo_detector import YOLO_DETECTOR
from runner.steps.geometry.area_calculator import AREA_CALCULATOR
from runner.steps.geometry.scale_detector import SCALE_DETECTOR
from runner.steps.geometry.walls_analyzer import WALLS_ANALYZER
from runner.steps.measurements.walls_measurer import WALLS_MEASURER
from runner.steps.pricing.house_summary import HOUSE_SUMMARY
from runner.steps.pricing.openings_pricer import OPENINGS_PRICER
from runner.steps.pricing.roof_pricer import ROOF_PRICER
from runner.steps.pricing.services_pricer import (
    ELECTRICITY_PRICER,
    HEATING_PRICER,
    SEWAGE_PRICER,
)
from runner.steps.pricing.walls_pricer import WALLS_PRICER
from runner.utils import logging as runner_logging
from runner.workers.plan_worker import PlanWorker, run_parallel


PIPELINE: list[PipelineStep] = [
    SCALE_DETECTOR,
    YOLO_DETECTOR,
    OPENINGS_HYBRID,
    PLAN_REFINER,
    EXTERIOR_CLASSIFIER,
    WALLS_ANALYZER,
    AREA_CALCULATOR,
    WALLS_MEASURER,
    OPENINGS_PRICER,
    WALLS_PRICER,
    ROOF_PRICER,
    ELECTRICITY_PRICER,
    HEATING_PRICER,
    SEWAGE_PRICER,
    HOUSE_SUMMARY,
]


def _build_workers(settings: RunnerSettings, plans: Iterable[Path]) -> list[PlanWorker]:
    plans_list = list(plans)
    workers = []
    total = len(plans_list)
    for idx, plan in enumerate(plans_list, start=1):
        workers.append(PlanWorker(settings=settings, plan_path=plan, index=idx, total=total))
    return workers


def _run_stage(step: PipelineStep, workers: list[PlanWorker]) -> None:
    runner_logging.begin_stage(step.stage_key, step.name, step.description)
    run_parallel(workers, step.script, step.name)
    runner_logging.finalize_stage(step.stage_key)


def run_pipeline() -> None:
    settings = RunnerSettings.load()
    detection = detect_plans(settings)
    worker_plans = _build_workers(settings, detection.plans)

    for step in PIPELINE:
        _run_stage(step, worker_plans)

    plans_merger.merge(settings)
    pdf_generator.generate(settings)
    runner_logging.log("Pipeline finalizat cu succes")


if __name__ == "__main__":
    run_pipeline()
