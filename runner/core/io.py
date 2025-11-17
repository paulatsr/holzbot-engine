#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
runner/core/io.py
Utilitare I/O standard pentru pipeline (fără dependență de orchestrator).

Expune:
- get_env(), project_root(), runs_root(), run_dir()
- current_plan_id(), current_plan_path()
- path_in_run(), plan_out_dir()
- read_json(), write_json()
- load_image(), save_image()
- ensure_dir()

Toate scripturile din runner/* pot folosi aceste funcții, evitând
hardcodarea lui "plan.jpg" și a căilor.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, Union

# opțional OpenCV; dacă nu e disponibil, folosim PIL ca fallback
try:
    import cv2  # type: ignore
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

try:
    from PIL import Image  # type: ignore
    import numpy as _np  # type: ignore
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


# ---------------- ENV helpers ----------------

def get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    val = os.environ.get(key, default)
    if required and (val is None or str(val).strip() == ""):
        raise RuntimeError(f"ENV missing: {key}")
    return val


def project_root() -> Path:
    # .../engine
    return Path(__file__).resolve().parents[2]


def runs_root() -> Path:
    # WORKDIR are prioritate; apoi RUNS_ROOT; apoi <PROJECT_ROOT>/runs
    wrk = get_env("WORKDIR") or get_env("RUNS_ROOT")
    return Path(wrk).expanduser().resolve() if wrk else (project_root() / "runs").resolve()


def run_dir() -> Path:
    run_id = get_env("RUN_ID", required=True)
    return (runs_root() / str(run_id)).resolve()


def current_plan_id(required: bool = True) -> Optional[str]:
    return get_env("PLAN_ID", required=required)


def current_plan_path(required: bool = True) -> Optional[Path]:
    p = get_env("PLAN_IMAGE", required=required)
    return Path(p).expanduser().resolve() if p else None


# ---------------- Path helpers ----------------

def ensure_dir(p: Union[str, Path]) -> Path:
    p = Path(p)
    p.mkdir(parents=True, exist_ok=True)
    return p


def path_in_run(*parts: str) -> Path:
    return (run_dir().joinpath(*parts)).resolve()


def plan_out_dir(*sub: str) -> Path:
    """
    Director standard pentru artefactele planului curent:
    runs/<RUN_ID>/plans/<PLAN_ID>/<sub...>
    """
    pid = current_plan_id(required=True)
    base = path_in_run("plans", str(pid))
    return ensure_dir(base.joinpath(*sub))


# ---------------- JSON helpers ----------------

def read_json(p: Union[str, Path]) -> Any:
    p = Path(p)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(obj: Any, p: Union[str, Path], pretty: bool = True) -> Path:
    p = Path(p)
    ensure_dir(p.parent)
    with p.open("w", encoding="utf-8") as f:
        if pretty:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        else:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return p


# ---------------- Image helpers ----------------

def load_image(path: Union[str, Path]):
    """
    Încărcă imaginea ca:
      - cv2 (BGR) dacă cv2 e instalat
      - np.ndarray RGB dacă avem doar PIL
    """
    path = str(path)
    if _HAS_CV2:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Nu pot citi imaginea: {path}")
        return img  # BGR
    if _HAS_PIL:
        im = Image.open(path).convert("RGB")
        return _np.array(im)  # RGB
    raise RuntimeError("Nu există nici cv2, nici PIL pentru a încărca imagini.")


def save_image(img, path: Union[str, Path]) -> Path:
    """
    Salvează imaginea:
      - cu cv2 dacă e disponibil (BGR)
      - altfel cu PIL (convertit RGB)
    """
    p = Path(path)
    ensure_dir(p.parent)
    if _HAS_CV2:
        ok = cv2.imwrite(str(p), img)
        if not ok:
            raise RuntimeError(f"Eșec la scrierea imaginii: {p}")
        return p
    if _HAS_PIL:
        if isinstance(img, Image.Image):
            im = img
        else:
            im = Image.fromarray(img)
        im.save(str(p))
        return p
    raise RuntimeError("Nu există nici cv2, nici PIL pentru a salva imagini.")


# ---------------- Convenience pentru pași ----------------

def current_plan_image_or_raise():
    """
    One-liner folosit în pași:
        img = current_plan_image_or_raise()
    Returnează imaginea încărcată a planului curent.
    """
    p = current_plan_path(required=True)
    return load_image(p)
