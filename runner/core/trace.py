#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
core/trace.py
--------------
Utilitar mic de logare + markers pentru UI (dacă ui_export este disponibil).
Folosit în runner/detect_plans_v2.py, runner/multi_plan_runner.py, etc.

Exemple:
    from runner.core.trace import tracer

    tracer.info("Pornesc detectarea planurilor...")
    with tracer.stage("export_objects", title="Extracție exemple", plan_hint="..."):
        # ...rulezi pașii tăi...
        tracer.image("/abs/path/plan.jpg")
        tracer.text("Am terminat pasul X")

Notă: mesajele merg la stdout (flush=True) pentru streaming live.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, ContextManager

# încercăm să aducem ui_export, dar nu e obligatoriu
try:
    from ui_export import begin_stage as _begin_stage
    from ui_export import finalize_stage as _finalize_stage
    from ui_export import record_text as _record_text
    from ui_export import record_image as _record_image
    _UI_OK = True
except Exception:
    _UI_OK = False
    _begin_stage = _finalize_stage = _record_text = _record_image = None  # type: ignore


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


@dataclass
class _Tracer:
    prefix: str = "TRACE"

    # ------------ console ------------
    def _println(self, level: str, msg: str) -> None:
        sys.stdout.write(f"[{_ts()}] [{self.prefix}] [{level}] {msg}\n")
        sys.stdout.flush()

    def info(self, msg: str) -> None:
        self._println("INFO", msg)

    def warn(self, msg: str) -> None:
        self._println("WARN", f"⚠️ {msg}")

    def err(self, msg: str) -> None:
        self._println("ERR", f"❌ {msg}")

    def ok(self, msg: str) -> None:
        self._println("OK", f"✅ {msg}")

    # ------------ UI helpers (no-op dacă ui_export lipsește) ------------
    def text(self, msg: str, stage: Optional[str] = None, filename: str = "_live.txt") -> None:
        if _UI_OK and stage:
            try:
                _record_text(msg, stage=stage, filename=filename, append=True)  # type: ignore
            except Exception:
                pass
        self.info(msg)

    def image(self, img_path: str | Path, stage: Optional[str] = None) -> None:
        if _UI_OK and stage:
            try:
                _record_image(str(img_path), stage=stage)  # type: ignore
            except Exception:
                pass
        self.info(f"[IMG] {img_path}")

    # ------------ stage context ------------
    class _Stage(ContextManager["_Stage"]):
        def __init__(self, outer: "_Tracer", key: str, title: Optional[str], plan_hint: Optional[str]) -> None:
            self._outer = outer
            self.key = key
            self.title = title or key
            self.plan_hint = plan_hint or ""

        def __enter__(self) -> "_Stage":
            if _UI_OK:
                try:
                    _begin_stage(self.key, title=self.title, plan_hint=self.plan_hint)  # type: ignore
                except Exception:
                    pass
            self._outer.info(f"== BEGIN STAGE: {self.key} | {self.title}")
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            if exc:
                self._outer.err(f"Stage '{self.key}' a ieșit cu eroare: {exc}")
            if _UI_OK:
                try:
                    _finalize_stage(self.key)  # type: ignore
                except Exception:
                    pass
            self._outer.info(f"== END STAGE: {self.key}")

    def stage(self, key: str, title: Optional[str] = None, plan_hint: Optional[str] = None) -> "_Stage":
        """
        Context manager pentru a marca un stage în UI + consolă.
        """
        return _Tracer._Stage(self, key, title, plan_hint)


# Instanță globală ușor de importat
tracer = _Tracer()
