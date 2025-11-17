#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
core/config.py
---------------
Config + settings centralizate pentru workflow.

Expune:
  - Settings: dataclass imutabilă care agregă toți parametrii importanți
  - Settings.from_env(): construiește Settings din variabilele de mediu / defaults
  - utilitare mici pentru parsing (bool/int/path)

Note:
  - PROJECT_ROOT este folderul în care rulează engine-ul (acest repo).
  - RUNS_ROOT este rădăcina unde se scriu rularile (runs/<RUN_ID>).
  - RUN_ID identifică o rulare; dacă lipsește, se generează local_XXXXXXXX.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    vv = v.strip().lower()
    return vv in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return int(v.strip())
    except Exception:
        return default


def _coalesce(*vals: Optional[str], default: str = "") -> str:
    for v in vals:
        if v and str(v).strip():
            return str(v).strip()
    return default


@dataclass(frozen=True)
class Settings:
    # --- IDs & roots ---
    project_root: Path
    runs_root: Path
    run_id: str

    # --- mirrors / api env (opțional) ---
    api_url: str
    engine_secret: str
    public_bucket_url: str
    offer_id: str

    # --- runtime behaviour ---
    log_level: str = "INFO"
    python_unbuffered: bool = True

    @property
    def run_dir(self) -> Path:
        p = self.runs_root / self.run_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    # === factories ===
    @staticmethod
    def from_env() -> "Settings":
        """
        Citește .env (dacă e deja încărcat în proces) și environment-ul curent.
        Nu încarcă explicit .env aici (runner_http.py o face deja), dar safe dacă
        nu este încărcat.
        """
        # PROJECT_ROOT = folderul acestui fișier (…/engine)
        # de obicei vrei root-ul repo-ului (parent).
        project_root = Path(__file__).resolve().parents[2]  # engine/runner/core -> engine -> <repo root>
        project_root_env = os.getenv("PROJECT_ROOT", "")
        if project_root_env:
            try:
                project_root = Path(project_root_env).resolve()
            except Exception:
                pass

        # RUNS_ROOT: poate veni din RUNS_ROOT sau WORKDIR; dacă lipsesc -> <PROJECT_ROOT>/runs
        runs_root_env = _coalesce(os.getenv("RUNS_ROOT"), os.getenv("WORKDIR"))
        runs_root = Path(runs_root_env).resolve() if runs_root_env else (project_root / "runs")
        runs_root.mkdir(parents=True, exist_ok=True)

        # RUN_ID: generăm dacă lipsește (pentru rulări locale)
        run_id_env = os.getenv("RUN_ID", "").strip()
        if not run_id_env:
            run_id_env = f"local_{int(time.time())}"

        # API / auth (opțional)
        api_url = (_coalesce(os.getenv("API_URL")).rstrip("/"))
        engine_secret = _coalesce(os.getenv("ENGINE_SECRET"))
        public_bucket_url = (_coalesce(os.getenv("PUBLIC_BUCKET_URL")).rstrip("/"))
        offer_id = _coalesce(os.getenv("OFFER_ID"))

        # Logging
        log_level = _coalesce(os.getenv("LOG_LEVEL"), default="INFO").upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            log_level = "INFO"

        # Unbuffered Python I/O pentru streaming live
        if os.getenv("PYTHONUNBUFFERED") is None:
            os.environ["PYTHONUNBUFFERED"] = "1"

        return Settings(
            project_root=project_root,
            runs_root=runs_root,
            run_id=run_id_env,
            api_url=api_url,
            engine_secret=engine_secret,
            public_bucket_url=public_bucket_url,
            offer_id=offer_id,
            log_level=log_level,
            python_unbuffered=True,
        )

    # === helpers ===
    def env_as_dict(self) -> dict:
        """
        Conversie în env dict – util dacă vrei să pornești subprocese cu aceleași variabile.
        """
        env = os.environ.copy()
        env["RUN_ID"] = self.run_id
        env["RUNS_ROOT"] = str(self.runs_root)
        env["PYTHONUNBUFFERED"] = "1"

        if self.api_url:
            env["API_URL"] = self.api_url
        if self.engine_secret:
            env["ENGINE_SECRET"] = self.engine_secret
        if self.public_bucket_url:
            env["PUBLIC_BUCKET_URL"] = self.public_bucket_url
        if self.offer_id:
            env["OFFER_ID"] = self.offer_id

        # Conveniență pentru UI
        env["UI_RUN_DIR"] = self.run_id
        env.setdefault("PYTHONPATH", str(self.project_root))
        return env
