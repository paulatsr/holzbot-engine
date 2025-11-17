#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
detect_plans.py
================
Rulează DOAR segmentarea/rafinarea planurilor și persistă lista de căi către planurile
rafinate în runs/<RUN_ID>/plans_list.json, pentru a fi folosită ulterior de run_all_cadrans.py.

ENV de interes:
- RUN_ID             (obligatoriu în context server; dacă lipsește → local_<ts> pentru CLI)
- RUNS_ROOT          (opțional; dacă lipsește => ./runs lângă acest fișier)
- SEGMENT_INPUT_PATH (opțional; dacă lipsește încearcă runs/<RUN_ID>/segment_input.* sau plan.jpg)
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

def ts():
    from datetime import datetime as _dt
    return _dt.now().strftime("%H:%M:%S.%f")[:-3]

def trace(msg: str):
    print(f"[{ts()}] [TRACE detect_plans] {msg}", flush=True)


def _write_plans_list(RUN_DIR: Path, plans: list[str]):
    out = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "plan_count": len(plans),
        "plans": plans,
    }
    (RUN_DIR / "plans_list.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"📝 Scris: {RUN_DIR / 'plans_list.json'}", flush=True)


def _detect_segment_input(RUN_DIR: Path) -> Path | None:
    """
    Găsește inputul pentru segmentare în ordine:
      1) SEGMENT_INPUT_PATH (env)
      2) runs/<RUN_ID>/segment_input.*
      3) runs/<RUN_ID>/plan.jpg
      4) engine/plan.jpg (lângă acest fișier)
    """
    seg_input_env = os.getenv("SEGMENT_INPUT_PATH", "").strip()
    seg_input_path: Path | None = None

    if seg_input_env:
        p = Path(seg_input_env)
        if p.exists():
            seg_input_path = p
            trace(f"SEGMENT_INPUT_PATH (env) = {seg_input_path}")
        else:
            trace(f"⚠️ SEGMENT_INPUT_PATH nu există pe disc: {p}")

    if seg_input_path is None:
        # încearcă mirror-ul salvat de runner_http: runs/<RUN_ID>/segment_input.ext
        for cand in RUN_DIR.glob("segment_input.*"):
            if cand.is_file():
                seg_input_path = cand
                trace(f"Folosesc {seg_input_path} din RUN_DIR")
                break

    if seg_input_path is None:
        # fallback: runs/<RUN_ID>/plan.jpg
        if (RUN_DIR / "plan.jpg").exists():
            seg_input_path = RUN_DIR / "plan.jpg"
            trace(f"Folosesc fallback {seg_input_path}")
        else:
            # fallback: ./plan.jpg lângă acest fișier
            proj_root = Path(__file__).resolve().parent
            engine_plan = proj_root / "plan.jpg"
            if engine_plan.exists():
                seg_input_path = engine_plan
                trace(f"Folosesc fallback engine/plan.jpg: {seg_input_path}")

    return seg_input_path


def main():
    run_id = os.getenv("RUN_ID", "").strip()
    if not run_id:
        # permis pentru rulare locală / CLI
        run_id = f"local_{int(datetime.utcnow().timestamp())}"
        trace(f"RUN_ID lipsea în env → folosesc {run_id}")

    runs_root_env = os.getenv("RUNS_ROOT", "").strip()
    RUNS_ROOT = Path(runs_root_env) if runs_root_env else (Path(__file__).resolve().parent / "runs")
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)

    RUN_DIR = RUNS_ROOT / run_id
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    trace(f"RUN_ID={run_id}")
    trace(f"RUNS_ROOT={RUNS_ROOT}")
    trace(f"RUN_DIR={RUN_DIR}")

    seg_input_path = _detect_segment_input(RUN_DIR)
    if seg_input_path is None:
        print("❌ Nu am găsit niciun input pentru segmentare.", flush=True)
        sys.exit(3)

    # import lazy ca să nu aducem dependințe inutile dacă doar citim jsonul
    try:
        from plan_segmentation import process_input as seg_process_input
    except Exception as e:
        trace(f"❌ Nu pot importa plan_segmentation: {e}")
        # fallback simplu: single-plan, fără segmentare
        plans = [str(seg_input_path)]
        _write_plans_list(RUN_DIR, plans)
        print("ℹ️ Folosesc single-plan fallback (nu am putut importa segmentarea).", flush=True)
        return

    seg_output_dir = RUN_DIR / "segmentation"
    seg_output_dir.mkdir(parents=True, exist_ok=True)

    trace(f"SEGMENTARE: process_input('{seg_input_path}', output_dir='{seg_output_dir}')")
    try:
        plans = seg_process_input(str(seg_input_path), output_dir=str(seg_output_dir)) or []
    except Exception as e:
        trace(f"⚠️ Eroare la segmentare: {e}")
        plans = []

    if not plans:
        trace("ℹ️ Segmentarea nu a returnat planuri rafinate → fallback single-plan.")
        plans = [str(seg_input_path)]

    # normalizăm în path absolut (ca să fie safe indiferent de cwd)
    plans = [str(Path(p).resolve()) for p in plans]

    _write_plans_list(RUN_DIR, plans)

    print(f"✅ Detectare finalizată. planuri={len(plans)} | runs/{run_id}/plans_list.json", flush=True)


if __name__ == "__main__":
    main()
