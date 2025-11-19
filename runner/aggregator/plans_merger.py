from __future__ import annotations

import json
from pathlib import Path

from runner.config.settings import RunnerSettings
from runner.utils import logging as runner_logging


def merge(settings: RunnerSettings) -> Path:
    price_summary = settings.project_root / "area/price_summary_full.json"
    run_out = settings.run_dir / "aggregated_summary.json"

    if not price_summary.exists():
        raise FileNotFoundError(f"Lipsește price_summary_full.json la {price_summary}")

    data = json.loads(price_summary.read_text(encoding="utf-8"))
    run_out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    runner_logging.log(f"Aggregated summary salvat în {run_out}")
    return run_out


if __name__ == "__main__":
    settings = RunnerSettings.load()
    merge(settings)
