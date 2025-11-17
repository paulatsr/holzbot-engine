#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
core/settings.py
----------------
Config centralizat pentru workflow.

Expune:
  - Settings (dataclass) – citește ENV, calculează directoare, validează.
  - load_settings() -> Settings – helper convenabil.

ENV cheie acceptate:
  RUN_ID              (obligatoriu în server; CLI poate genera local_<ts>)
  RUNS_ROOT           (rădăcina tuturor rulărilor; default: <project>/runs)
  WORKDIR             (alias pentru RUNS_ROOT; dacă ambele setate, câștigă RUNS_ROOT)
  SEGMENT_INPUT_PATH  (opțional; dacă e setat sare peste autodetect local)
  API_URL             (opțional; pentru upload/integrare backend)
  ENGINE_SECRET       (opțional; pentru autentificare către backend)
  OFFER_ID            (opțional; ID ofertă curentă)
  PUBLIC_BUCKET_URL   (opțional; URL public storage)
  LOG_LEVEL           (DEBUG|INFO|WARNING|ERROR, default INFO)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from datetime import datetime


def _project_root() -> Path:
    # presupunem că fișierul se află în engine/runner/core/settings.py
    return Path(__file__).resolve().parents[3]


def _coalesce(*vals: Optional[str]) -> str:
    for v in vals:
        if v and str(v).strip():
            return str(v).strip()
    return ""


@dataclass
class Settings:
    # identitate & căi
    run_id: str
    project_root: Path
    runs_root: Path
    run_dir: Path

    # integrare backend (opțional)
    api_url: str = ""
    engine_secret: str = ""
    public_bucket_url: str = ""
    offer_id: str = ""

    # input segmentare (opțional)
    segment_input_path: str = ""

    # logger
    log_level: str = "INFO"

    # derivări utile
    plan_count: int = 0

    @property
    def has_backend(self) -> bool:
        return bool(self.api_url and self.engine_secret)

    def ensure_dirs(self) -> None:
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def describe(self) -> str:
        return (
            f"Settings(run_id={self.run_id}, runs_root={self.runs_root}, run_dir={self.run_dir}, "
            f"backend={'yes' if self.has_backend else 'no'}, log={self.log_level})"
        )


def _resolve_runs_root(project_root: Path) -> Path:
    # Prioritate: RUNS_ROOT > WORKDIR > <project>/runs
    rr = _coalesce(os.getenv("RUNS_ROOT"), os.getenv("WORKDIR"))
    return Path(rr) if rr else (project_root / "runs")


def _resolve_run_id() -> str:
    rid = _coalesce(os.getenv("RUN_ID"))
    if rid:
        return rid
    # CLI fallback
    return f"local_{int(datetime.utcnow().timestamp())}"


def _normalize_abs_or_empty(path_str: str, base: Path) -> str:
    if not path_str:
        return ""
    p = Path(path_str)
    return str(p if p.is_absolute() else (base / p).resolve())


def load_settings() -> Settings:
    project = _project_root()
    run_id = _resolve_run_id()
    runs_root = _resolve_runs_root(project).resolve()
    run_dir = (runs_root / run_id).resolve()

    api = _coalesce(os.getenv("API_URL"))
    secret = _coalesce(os.getenv("ENGINE_SECRET"))
    bucket = _coalesce(os.getenv("PUBLIC_BUCKET_URL"))
    offer = _coalesce(os.getenv("OFFER_ID"))
    seg_input = _normalize_abs_or_empty(_coalesce(os.getenv("SEGMENT_INPUT_PATH")), runs_root)
    log_level = (_coalesce(os.getenv("LOG_LEVEL")) or "INFO").upper()

    s = Settings(
        run_id=run_id,
        project_root=project,
        runs_root=runs_root,
        run_dir=run_dir,
        api_url=api.rstrip("/"),
        engine_secret=secret,
        public_bucket_url=bucket.rstrip("/"),
        offer_id=offer,
        segment_input_path=seg_input,
        log_level=log_level,
    )
    s.ensure_dirs()
    return s
