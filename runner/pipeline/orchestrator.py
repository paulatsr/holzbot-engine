#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
runner/pipeline/orchestrator.py
Orchestrator fără „cadrane” și fără copiere în plan.jpg.

- Citește runs/<RUN_ID>/plans_list.json (scris de runner/detection/detect_plans.py)
- Pentru fiecare plan, setează ENV:
      PLAN_INDEX, PLAN_ID, PLAN_IMAGE, PLAN_COUNT
- Rulează pașii în ordinea specificată mai jos; fiecare pas trebuie să
  citească imaginea din os.environ["PLAN_IMAGE"] (NU din plan.jpg).
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

from runner.core.env import Env

HERE = Path(__file__).resolve().parent        # .../engine/runner/pipeline
PRJ  = HERE.parent.parent                     # .../engine

def _load_plans_list(run_dir: Path) -> list[str]:
    p = run_dir / "plans_list.json"
    if not p.exists():
        raise RuntimeError("Lipsește runs/<RUN_ID>/plans_list.json — rulează întâi runner/detection/detect_plans.py")
    data = json.loads(p.read_text(encoding="utf-8"))
    plans = data.get("plans") or []
    if not plans:
        raise RuntimeError("plans_list.json nu conține planuri")
    return [str(Path(x)) for x in plans]

def _run_step(py: str, rel_script: str, osenv: dict) -> None:
    cmd = [py, "-u", rel_script]
    proc = subprocess.Popen(
        cmd, cwd=str(PRJ), env=osenv,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"Step failed: {rel_script} (exit {code})")

def main():
    env = Env.load(project_root=PRJ)
    env.ensure_dirs()

    py = env.python_bin()
    osenv = env.for_subprocess()

    plans = _load_plans_list(env.RUN_DIR)
    total = len(plans)
    osenv["PLAN_COUNT"] = str(total)

    # —— Ordinea pașilor (ajusteaz-o după nevoi) ——
    steps_order = [
        # DETECTION / OPENINGS
        "runner/detection/detect_openings_hybrid.py",
        "runner/detection/export_templates_from_detections.py",
        "runner/detection/import_yolo_detections.py",

        # GEOMETRY
        "runner/geometry/scale_from_plan.py",
        "runner/geometry/walls_length_from_plan.py",
        "runner/geometry/house_area_from_plan.py",

        # SEGMENTATION
        "runner/segmentation/classify_exterior_doors.py",
        "runner/segmentation/plan_segmentation.py",

        # OPENINGS pricing / normalize
        "runner/openings/openings_pricing.py",

        # AREAS
        "runner/areas/walls_area_from_lenghts.py",
        "runner/areas/walls_area_with_openings.py",

        # ROOF
        "runner/roof/roof_price_from_area.py",

        # SERVICES
        "runner/services/electricity_from_area.py",
        "runner/services/heating_from_area.py",
        "runner/services/sewage_from_area.py",

        # PRICING + EVALUATION
        "runner/pricing/house_price_summary.py",
        "runner/evaluation/evaluate_house_plan.py",
    ]

    for idx, plan_path in enumerate(plans, start=1):
        plan_id = f"p{idx:02d}"
        osenv.update({
            "PLAN_INDEX": str(idx),
            "PLAN_ID": plan_id,
            "PLAN_IMAGE": str(plan_path),  # <- sursa adevărată a imaginii
            "PLAN_COUNT": str(total),
        })

        print("\n===============================")
        print(f"🏠 PLAN {idx}/{total} — {plan_id}")
        print(f"PLAN_IMAGE: {plan_path}")
        print("===============================\n")

        for rel in steps_order:
            print(f"\n→ RUN {rel} (plan {idx}/{total})")
            _run_step(py, rel, osenv)

    print("\n✅ All plans processed (fără plan.jpg).")

if __name__ == "__main__":
    main()
