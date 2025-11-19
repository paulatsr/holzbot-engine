from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List

from runner.config.settings import RunnerSettings
from runner.utils import logging as runner_logging


@dataclass
class PlanWorker:
    settings: RunnerSettings
    plan_path: Path
    index: int
    total: int

    @property
    def plan_id(self) -> str:
        return f"p{self.index:02d}"

    def env(self) -> dict:
        base = self.settings.env(
            {
                "PLAN_INDEX": str(self.index),
                "PLAN_ID": self.plan_id,
                "PLAN_IMAGE": str(self.plan_path),
                "PLAN_COUNT": str(self.total),
            }
        )
        return base

    def run_script(self, script: str, title: str) -> None:
        env = self.env()
        cmd = [self.settings.python_bin, "-u", script]
        runner_logging.log(f"START {title} | plan={self.plan_id} | cmd={' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.settings.project_root),
            env=env,
            stdout=None,
            stderr=None,
        )
        ret = proc.wait()
        runner_logging.log(f"END {title} | plan={self.plan_id} | exit={ret}")
        if ret != 0:
            raise RuntimeError(f"Step '{title}' failed for plan {self.plan_id} (exit={ret})")


def run_parallel(workers: Iterable[PlanWorker], script: str, title: str) -> None:
    worker_list = list(workers)
    def _execute(worker: PlanWorker) -> None:
        worker.run_script(script, title)

    if not worker_list:
        return

    with ThreadPoolExecutor(max_workers=len(worker_list)) as executor:
        futures: List[Future] = []
        for worker in worker_list:
            futures.append(executor.submit(_execute, worker))
        for fut in futures:
            fut.result()


def run_for_plans(callback: Callable[[], None]) -> None:
    plans_env = os.getenv("MULTI_PLANS")
    plan_image = os.getenv("PLAN_IMAGE")

    if plan_image and not plans_env:
        callback()
        return

    if not plans_env:
        callback()
        return

    plans = [p.strip() for p in plans_env.split(",") if p.strip()]
    if not plans:
        callback()
        return

    prev_env = os.environ.copy()
    try:
        total = len(plans)
        for idx, plan in enumerate(plans, start=1):
            os.environ["PLAN_INDEX"] = str(idx)
            os.environ["PLAN_ID"] = f"p{idx:02d}"
            os.environ["PLAN_IMAGE"] = plan
            os.environ["PLAN_COUNT"] = str(total)
            callback()
    finally:
        os.environ.clear()
        os.environ.update(prev_env)
