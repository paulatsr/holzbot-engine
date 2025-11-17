#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
detection/detect_plans.py
-------------------------
Face DOAR detectarea/segmentarea planurilor și salvează lista rezultată în:
  runs/<RUN_ID>/plans_list.json

Integrare:
  - Folosește core/env.Env pentru RUN_ID/RUN_DIR etc.
  - Opțional citește SEGMENT_INPUT_PATH din ENV;
  - Dacă lipsește, caută în runs/<RUN_ID>/segment_input.* sau runs/<RUN_ID>/plan.jpg
  - Fallback la PROJECT_ROOT/plan.jpg

Output JSON:
{
  "generated_at": "...Z",
  "plan_count": <int>,
  "plans": ["<abs path crop1>", "<abs path crop2>", ...]
}
"""

from __future__ import annotations
import os
import sys
import json
from pathlib import Path
from datetime import datetime

from core.env import Env
from core.proc import _banner  # banner pentru STDOUT (dacă nu-l ai, înlocuiește cu print)

def ts():
    from datetime import datetime as _dt
    return _dt.now().strftime("%H:%M:%S.%f")[:-3]

def trace(msg: str):
    print(f"[{ts()}] [TRACE detect_plans] {msg}", flush=True)

def _write_plans_list(out_path: Path, plans: list[str]) -> None:
    out = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "plan_count": len(plans),
        "plans": plans,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📝 Scris: {out_path}", flush=True)

def _detect_segment_input(env: Env) -> Path | None:
    """
    Găsește inputul pentru segmentare în ordine:
      1) SEGMENT_INPUT_PATH (env)
      2) runs/<RUN_ID>/segment_input.*
      3) runs/<RUN_ID>/plan.jpg
      4) PROJECT_ROOT/plan.jpg
    """
    seg_input_path: Path | None = None

    if env.SEGMENT_INPUT_PATH and env.SEGMENT_INPUT_PATH.exists():
        seg_input_path = env.SEGMENT_INPUT_PATH
        trace(f"SEGMENT_INPUT_PATH (env) = {seg_input_path}")
    elif env.SEGMENT_INPUT_PATH:
        trace(f"⚠️ SEGMENT_INPUT_PATH nu există: {env.SEGMENT_INPUT_PATH}")

    if seg_input_path is None:
        for cand in env.RUN_DIR.glob("segment_input.*"):
            if cand.is_file():
                seg_input_path = cand
                trace(f"Folosesc {seg_input_path} din RUN_DIR")
                break

    if seg_input_path is None:
        fallback_run = env.RUN_DIR / "plan.jpg"
        if fallback_run.exists():
            seg_input_path = fallback_run
            trace(f"Folosesc fallback {seg_input_path}")

    if seg_input_path is None:
        engine_plan = env.PROJECT_ROOT / "plan.jpg"
        if engine_plan.exists():
            seg_input_path = engine_plan
            trace(f"Folosesc fallback PROJECT_ROOT/plan.jpg: {seg_input_path}")

    return seg_input_path

def main() -> int:
    print(_banner("🏗️  DETECT PLANS — segmentare + listare rezultate"))
    env = Env.load()
    env.ensure_dirs()

    print(f"RUN_ID={env.RUN_ID}")
    print(f"RUNS_ROOT={env.RUNS_ROOT}")
    print(f"RUN_DIR={env.RUN_DIR}")

    seg_input_path = _detect_segment_input(env)
    if seg_input_path is None:
        print("❌ Nu am găsit niciun input pentru segmentare.", flush=True)
        return 3

    # import lazy: folosim pipeline-ul tău existent
    try:
        from plan_segmentation import process_input as seg_process_input
    except Exception as e:
        trace(f"❌ Nu pot importa plan_segmentation: {e}")
        # fallback simplu: single-plan
        plans = [str(seg_input_path.resolve())]
        _write_plans_list(env.path_in_run("plans_list.json"), plans)
        print("ℹ️ Folosesc single-plan fallback (nu am putut importa segmentarea).", flush=True)
        print("✅ Detectare finalizată (fallback).")
        return 0

    # director de output pentru segmentare per RUN_ID
    seg_output_dir = env.path_in_run("segmentation")
    seg_output_dir.mkdir(parents=True, exist_ok=True)

    trace(f"SEGMENTARE: process_input('{seg_input_path}', output_dir='{seg_output_dir}')")
    try:
        plans = seg_process_input(str(seg_input_path), output_dir=str(seg_output_dir)) or []
    except Exception as e:
        trace(f"⚠️ Eroare la segmentare: {e}")
        plans = []

    if not plans:
        trace("ℹ️ Segmentarea nu a returnat planuri rafinate → fallback single-plan.")
        plans = [str(seg_input_path.resolve())]

    # absolutizăm căile
    plans = [str(Path(p).resolve()) for p in plans]
    _write_plans_list(env.path_in_run("plans_list.json"), plans)

    print(f"✅ Detectare finalizată. planuri={len(plans)} | {env.path_in_run('plans_list.json')}", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
