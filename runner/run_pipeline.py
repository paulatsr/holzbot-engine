#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
runner/run_pipeline.py
Entrypoint unic al pipeline-ului (fără noțiunea de „cadrane”).

Pași:
  1) Detectează/rafinează planurile (runner/detection/detect_plans.py)
  2) Rulează pașii în lanț pentru TOATE planurile (runner/pipeline/orchestrator.py)
"""

from __future__ import annotations
import subprocess
import sys
from pathlib import Path

from runner.core.env import Env

HERE = Path(__file__).resolve().parent               # .../engine/runner
PRJ  = HERE.parent                                   # .../engine

def _run_blocking(cmd: list[str], cwd: Path, env: dict) -> int:
    proc = subprocess.Popen(
        cmd, cwd=str(cwd), env=env,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    return proc.wait()

def main():
    env = Env.load(project_root=PRJ)
    env.ensure_dirs()

    py = env.python_bin()
    osenv = env.for_subprocess()

    # 1) detectare + rafinare planuri → runs/<RUN_ID>/plans_list.json
    ret = _run_blocking([py, "-u", "runner/detection/detect_plans.py"], PRJ, osenv)
    if ret != 0:
        print(f"❌ detect_plans.py exit={ret}")
        sys.exit(ret)

    # 2) orchestrare (toți pașii, pentru toate planurile)
    ret = _run_blocking([py, "-u", "runner/pipeline/orchestrator.py"], PRJ, osenv)
    if ret != 0:
        print(f"❌ orchestrator.py exit={ret}")
        sys.exit(ret)

    print("✅ Pipeline finalizat.")

if __name__ == "__main__":
    main()
