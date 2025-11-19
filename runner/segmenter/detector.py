from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from runner.config.settings import RunnerSettings
from runner.utils import logging as runner_logging


@dataclass
class PlanDetectionResult:
    plans: list[Path]

    @property
    def count(self) -> int:
        return len(self.plans)


def detect_plans(settings: RunnerSettings) -> PlanDetectionResult:
    cmd = [settings.python_bin, "runner/detection/detect_plans.py"]
    runner_logging.log("Pornesc segmentarea inițială a planurilor")
    proc = subprocess.Popen(cmd, cwd=str(settings.project_root), env=settings.env({}))
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"detect_plans.py exit {ret}")

    manifest = settings.run_dir / "plans_list.json"
    if not manifest.exists():
        raise FileNotFoundError(f"Lipsește manifestul planurilor: {manifest}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    plans = [Path(p).resolve() for p in data.get("plans", [])]
    if not plans:
        raise RuntimeError("Lista de planuri este goală")
    runner_logging.log(f"Detectate {len(plans)} planuri")
    return PlanDetectionResult(plans=plans)
