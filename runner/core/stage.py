# engine/runner/core/stage.py
# -*- coding: utf-8 -*-
"""
Stage helpers pentru pipeline:
 - begin_stage / finalize_stage (dacă ui_export este disponibil)
 - run_step()  -> rulează un script cu streaming al stdout/stderr
 - run_scripts_for_plans() -> rulat aceeași listă de pași pentru toate planurile
"""

from __future__ import annotations
import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Iterable, List, Tuple, Dict, Optional

# -------- logging/trace (fallback pe print) --------
def _ts() -> str:
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def trace(msg: str) -> None:
    try:
        # dacă ai deja engine/runner/core/trace.py îl poți importa aici
        # from .trace import trace as _t; _t(msg); return
        pass
    except Exception:
        pass
    print(f"[{_ts()}] [STAGE] {msg}", flush=True)


# -------- UI hooks (opțional) --------
_begin_stage = _finalize_stage = _record_text = _record_image = None
try:
    # compatibil cu layout-ul tău existent (ui_export e opțional)
    from ui_export import begin_stage as _begin_stage, finalize_stage as _finalize_stage
    from ui_export import record_text as _record_text, record_image as _record_image
    trace("ui_export hooks active")
except Exception:
    trace("ui_export indisponibil – continui fără UI hooks")


def begin(stage_key: str, title: str, plan_hint: str = "") -> None:
    if _begin_stage:
        try:
            _begin_stage(stage_key, title=title, plan_hint=plan_hint or "")
        except Exception as e:
            trace(f"begin_stage failed (ignorat): {e}")


def finalize(stage_key: str) -> None:
    if _finalize_stage:
        try:
            _finalize_stage(stage_key)
        except Exception as e:
            trace(f"finalize_stage failed (ignorat): {e}")


def emit(stage_key: str, text: str = "", image_path: Optional[str] = None) -> None:
    if _record_text and text:
        try:
            _record_text(text, stage=stage_key, filename="_live.txt", append=True)
        except Exception:
            pass
    if _record_image and image_path:
        p = Path(image_path)
        if p.exists():
            try:
                _record_image(str(p), stage=stage_key)
            except Exception:
                pass


# -------- exec helpers --------
def _python_bin(project_root: Path) -> str:
    cand = project_root / ".venv" / "bin" / "python3"
    return str(cand) if cand.exists() else "python3"


def run_step(
    project_root: Path,
    rel_script: str,
    env: Optional[Dict[str, str]] = None,
    title: Optional[str] = None,
) -> None:
    """
    Rulează `python -u <rel_script>` cu cwd=project_root.
    Stream-uiește output în timp real. Aruncă RuntimeError dacă exit!=0.
    """
    python_bin = _python_bin(project_root)
    cmd = [python_bin, "-u", rel_script]
    t0 = time.perf_counter()

    trace(f"START step: {title or rel_script} | cmd={' '.join(cmd)} | cwd={project_root}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(project_root),
        env=env or os.environ.copy(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    ret = proc.wait()
    dt = time.perf_counter() - t0
    trace(f"END   step: {title or rel_script} | exit={ret} | duration={dt:.2f}s")
    if ret != 0:
        raise RuntimeError(f"❌ Step failed: {title or rel_script} (exit {ret})")


def set_plan_env(
    base_env: Dict[str, str],
    project_root: Path,
    plan_index: int,
    total_plans: int,
    plan_path: str,
) -> Dict[str, str]:
    """
    Pregătește ENV pentru un anumit plan + copiază planul în engine/plan.jpg
    pentru compatibilitate cu scripturi existente.
    """
    env = dict(base_env)
    plan_id = f"p{plan_index:02d}"
    env["PLAN_INDEX"] = str(plan_index)
    env["PLAN_ID"] = plan_id
    env["PLAN_IMAGE"] = str(plan_path)
    env["PLAN_COUNT"] = str(total_plans)

    dst = project_root / "plan.jpg"
    try:
        Path(plan_path).resolve().write_bytes(Path(plan_path).read_bytes())  # noop verify exist
        # copy sigur (fără shutil pentru a reduce dependențe)
        with open(plan_path, "rb") as src, open(dst, "wb") as out:
            out.write(src.read())
        trace(f"[PLAN {plan_index}/{total_plans}] set PLAN_IMAGE -> {dst.name}")
    except Exception as e:
        raise RuntimeError(f"Nu pot seta plan curent ({plan_path}) → {dst}: {e}")

    return env


def run_scripts_for_plans(
    project_root: Path,
    stage_key: str,
    stage_title: str,
    plan_hint: str,
    plans: List[str],
    scripts: List[Tuple[str, str]],
    base_env: Optional[Dict[str, str]] = None,
) -> None:
    """
    Rulează o listă de (nice_title, rel_script) pentru fiecare plan.
    """
    begin(stage_key, stage_title, plan_hint)
    total = len(plans)

    for idx, plan_path in enumerate(plans, start=1):
        env = set_plan_env(base_env or os.environ.copy(), project_root, idx, total, plan_path)

        # marker UI
        try:
            emit(stage_key, text=f"== START {stage_key} [{idx}/{total}] ==", image_path=plan_path)
        except Exception:
            pass

        for nice_title, rel_script in scripts:
            title = f"{nice_title} (PLAN {idx}/{total})"
            run_step(project_root, rel_script, env=env, title=title)

    finalize(stage_key)
