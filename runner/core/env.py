#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
core/env.py
-----------
Loader unificat pentru variabile de mediu + convenții de lucru:
- Rezolvă RUN_ID (fallback local_*)
- Alege RUNS_ROOT/WORKDIR și construiește RUN_DIR
- Normalizează căi (Path)
- Expune helpers pentru propagarea ENV către subprocese
- Opțional încarcă .env (dacă există python-dotenv)

Folosește-l din runner/evaluate_house_plan.py, detect_plans.py etc.:
    from runner.core.env import Env

    env = Env.load()              # citește env + .env, calculează defaulturi
    env.ensure_dirs()             # se asigură că RUNS_ROOT/RUN_DIR există
    os_env = env.for_subprocess() # dict gata de dat la subprocess.Popen(env=...)

"""

from __future__ import annotations

import os
import sys
import platform
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Optional

# -- încercăm să încărcăm .env (dacă e prezent) -------------------------------
try:
    from dotenv import load_dotenv  # type: ignore
    _DOTENV_OK = True
except Exception:
    _DOTENV_OK = False


def _coerce_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    v = val.strip().lower()
    if v in {"1", "true", "da", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "nu", "no", "n", "off"}:
        return False
    return default


def _safe_int(val: Optional[str], default: int) -> int:
    try:
        return int(str(val).strip())
    except Exception:
        return default


@dataclass
class Env:
    # Identitate rulare
    RUN_ID: str
    UI_RUN_DIR: str

    # Căi & workdirs
    PROJECT_ROOT: Path
    RUNS_ROOT: Path
    RUN_DIR: Path

    # Config API / securitate
    API_URL: str = ""
    ENGINE_SECRET: str = ""
    PUBLIC_BUCKET_URL: str = ""
    OFFER_ID: str = ""

    # Input segmentare
    SEGMENT_INPUT_PATH: Optional[Path] = None

    # Multi-plan
    PLAN_COUNT: int = 1

    # Alte setări
    PYTHONUNBUFFERED: str = "1"
    PYTHONPATH: str = field(default_factory=str)

    # Logging & debug
    DEBUG: bool = False
    TRACE: bool = False

    # Binare utile
    PYTHON_BIN: Optional[Path] = None  # .venv/bin/python (dacă există)

    @staticmethod
    def load(project_root: Optional[Path] = None) -> "Env":
        """
        Citește .env (dacă e posibil), apoi ENV, apoi aplică defaulturi.
        """
        prj = project_root or Path(__file__).resolve().parents[2]  # .../engine
        if _DOTENV_OK:
            # .env poate exista în engine/ sau în PROJECT_ROOT
            for cand in [prj / ".env", prj.parent / ".env"]:
                try:
                    if cand.exists():
                        load_dotenv(str(cand))
                except Exception:
                    pass

        # --- ID rulare ---
        run_id = (os.getenv("RUN_ID") or "").strip()
        if not run_id:
            import time
            run_id = f"local_{int(time.time())}"

        ui_run_dir = os.getenv("UI_RUN_DIR") or run_id

        # --- RUNS_ROOT/WORKDIR ---
        wrk = (os.getenv("WORKDIR") or os.getenv("RUNS_ROOT") or "").strip()
        if wrk:
            runs_root = Path(wrk).expanduser().resolve()
        else:
            runs_root = (prj / "runs").resolve()

        run_dir = (runs_root / run_id).resolve()

        # --- API/SEC ---
        api = (os.getenv("API_URL") or "").strip().rstrip("/")
        secret = (os.getenv("ENGINE_SECRET") or "").strip()
        bucket = (os.getenv("PUBLIC_BUCKET_URL") or "").strip().rstrip("/")
        offer_id = (os.getenv("OFFER_ID") or "").strip()

        # --- Input segmentare ---
        seg_in = (os.getenv("SEGMENT_INPUT_PATH") or "").strip()
        seg_path = Path(seg_in).expanduser().resolve() if seg_in else None

        # --- PLAN_COUNT ---
        plan_count = _safe_int(os.getenv("PLAN_COUNT"), 1)

        # --- Debug/Trace ---
        dbg = _coerce_bool(os.getenv("DEBUG"), False)
        trc = _coerce_bool(os.getenv("TRACE"), False)

        # --- Python bin preferat (.venv dacă există) ---
        venv_bin = (prj / ".venv" / ("Scripts" if platform.system() == "Windows" else "bin") / ("python.exe" if platform.system() == "Windows" else "python"))
        py_bin = venv_bin if venv_bin.exists() else None

        py_path = os.getenv("PYTHONPATH") or ""
        # asigurăm includerea PROJECT_ROOT în PYTHONPATH
        prj_str = str(prj)
        if prj_str not in py_path.split(os.pathsep):
            py_path = prj_str + (os.pathsep + py_path if py_path else "")

        return Env(
            RUN_ID=run_id,
            UI_RUN_DIR=ui_run_dir,
            PROJECT_ROOT=prj,
            RUNS_ROOT=runs_root,
            RUN_DIR=run_dir,
            API_URL=api,
            ENGINE_SECRET=secret,
            PUBLIC_BUCKET_URL=bucket,
            OFFER_ID=offer_id,
            SEGMENT_INPUT_PATH=seg_path,
            PLAN_COUNT=plan_count,
            PYTHONUNBUFFERED="1",
            PYTHONPATH=py_path,
            DEBUG=dbg,
            TRACE=trc,
            PYTHON_BIN=py_bin,
        )

    # ----------------- Helpers -----------------

    def ensure_dirs(self) -> None:
        self.RUNS_ROOT.mkdir(parents=True, exist_ok=True)
        self.RUN_DIR.mkdir(parents=True, exist_ok=True)

    def for_subprocess(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Dict ENV pregătit pentru subprocess.Popen(env=...).
        """
        env = os.environ.copy()
        env.update(
            {
                "RUN_ID": self.RUN_ID,
                "UI_RUN_DIR": self.UI_RUN_DIR,
                "PYTHONUNBUFFERED": self.PYTHONUNBUFFERED,
                "PYTHONPATH": self.PYTHONPATH,
                "WORKDIR": str(self.RUNS_ROOT),
                "RUNS_ROOT": str(self.RUNS_ROOT),
                "API_URL": self.API_URL,
                "ENGINE_SECRET": self.ENGINE_SECRET,
                "PUBLIC_BUCKET_URL": self.PUBLIC_BUCKET_URL,
                "OFFER_ID": self.OFFER_ID,
                "PLAN_COUNT": str(self.PLAN_COUNT),
            }
        )
        if self.SEGMENT_INPUT_PATH:
            env["SEGMENT_INPUT_PATH"] = str(self.SEGMENT_INPUT_PATH)
        if extra:
            env.update(extra)
        return env

    def python_bin(self) -> str:
        """
        Returnează binarul de Python preferat pentru rulări:
        - .venv/bin/python dacă există
        - altfel "python3" / "python" în funcție de platformă
        """
        if self.PYTHON_BIN and self.PYTHON_BIN.exists():
            return str(self.PYTHON_BIN)
        if platform.system() == "Windows":
            return "python"
        return "python3"

    # sugar
    def path_in_run(self, *parts: str) -> Path:
        return (self.RUN_DIR.joinpath(*parts)).resolve()

    def to_dict(self) -> Dict[str, str]:
        d = asdict(self).copy()
        # normalizăm pentru citire umană
        d["PROJECT_ROOT"] = str(self.PROJECT_ROOT)
        d["RUNS_ROOT"] = str(self.RUNS_ROOT)
        d["RUN_DIR"] = str(self.RUN_DIR)
        d["SEGMENT_INPUT_PATH"] = str(self.SEGMENT_INPUT_PATH) if self.SEGMENT_INPUT_PATH else ""
        d["PYTHON_BIN"] = str(self.PYTHON_BIN) if self.PYTHON_BIN else ""
        return d


# exec rapid pentru debugging manual
if __name__ == "__main__":
    e = Env.load()
    e.ensure_dirs()
    print("== ENV DUMP ==")
    for k, v in e.to_dict().items():
        print(f"{k:>22}: {v}")
