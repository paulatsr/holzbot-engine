#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
core/paths.py
-------------
Helperi centralizați pentru căi de fișiere/foldere în workflow.

Expune:
  - Paths: dataclass legată de Settings (core/config.py)
  - metode utile pentru:
      * runs/<RUN_ID>/...
      * planuri detectate (plans_list.json)
      * directoarele standard de engine (area/, roof/, perimeter/, etc.)
      * directoare temporare per-plan și per-etapă (stage buckets)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from .config import Settings


@dataclass(frozen=True)
class Paths:
    s: Settings

    # --- rădăcini ---
    @property
    def project_root(self) -> Path:
        return self.s.project_root

    @property
    def run_dir(self) -> Path:
        return self.s.run_dir

    @property
    def runs_root(self) -> Path:
        return self.s.runs_root

    # --- fișiere mirror UI / export ---
    def runs_export_json(self) -> Path:
        return self.run_dir / "export.json"

    def runs_merged_form_json(self) -> Path:
        return self.run_dir / "merged_form.json"

    def runs_segment_input(self) -> Optional[Path]:
        """
        Dacă runner_http a salvat inputul determinist pentru segmentare.
        Caută cele mai comune extensii.
        """
        for ext in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"):
            p = self.run_dir / f"segment_input{ext}"
            if p.exists():
                return p
        return None

    def runs_plan_jpg(self) -> Path:
        return self.run_dir / "plan.jpg"

    # --- detect_plans I/O ---
    def plans_list_json(self) -> Path:
        return self.run_dir / "plans_list.json"

    def segmentation_root(self) -> Path:
        """
        Folder unde detect_plans_v2/segmenter scrie artefactele job-ului.
        """
        p = self.run_dir / "segmentation"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def segmentation_job_dir(self) -> Path:
        """
        Subfolder per rulare (poți să îl folosești dacă vrei sesiuni multiple).
        Momentan folosim direct segmentation_root.
        """
        return self.segmentation_root()

    # --- stage dirs standard (UI/export pipeline) ---
    def stage_dir(self, stage_key: str) -> Path:
        """
        Exemplu: stage_key = "export_objects", "perimeter", "roof", etc.
        """
        p = self.project_root / stage_key
        p.mkdir(parents=True, exist_ok=True)
        return p

    # --- engine data (output consolidate) ---
    def area_dir(self) -> Path:
        p = self.project_root / "area"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def roof_dir(self) -> Path:
        p = self.project_root / "roof"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def perimeter_dir(self) -> Path:
        p = self.project_root / "perimeter"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def ui_out_dir(self) -> Path:
        p = self.project_root / "ui_out" / f"run_{self.s.run_id}"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # --- artefacte area/roof/walls folosite de house_pricing.py ---
    def house_area_single(self) -> Path:
        return self.area_dir() / "house_area_gemini.json"

    def house_area_multi(self, suffix: str) -> Path:
        """
        suffix: "", "_p01", "_p02"...
        """
        return self.area_dir() / f"house_area_gemini{suffix}.json"

    def wall_areas_single(self) -> Path:
        return self.area_dir() / "wall_areas_from_gemini.json"

    def wall_areas_multi(self, suffix: str) -> Path:
        return self.area_dir() / f"wall_areas_from_gemini{suffix}.json"

    def openings_all_single(self) -> Path:
        return self.perimeter_dir() / "openings_all.json"

    def openings_all_multi(self, suffix: str) -> Path:
        return self.perimeter_dir() / f"openings_all{suffix}.json"

    def roof_price_single(self) -> Path:
        return self.roof_dir() / "roof_price_estimation.json"

    def roof_price_multi(self, suffix: str) -> Path:
        return self.roof_dir() / f"roof_price_estimation{suffix}.json"

    # --- sistem & coeficienți ---
    def system_selected_json(self) -> Path:
        return self.area_dir() / "system_selected.json"

    def area_coefficients_json(self) -> Path:
        return self.area_dir() / "area_coefficients.json"

    def wall_coefficients_json(self) -> Path:
        return self.area_dir() / "wall_coefficients.json"

    def offer_coefficients_json(self) -> Path:
        return self.area_dir() / "offer_coefficients.json"

    def structure_coefficients_json(self) -> Path:
        return self.area_dir() / "structure_coefficients.json"

    def foundation_coefficients_json(self) -> Path:
        return self.area_dir() / "foundation_coefficients.json"

    def ventilation_coefficients_json(self) -> Path:
        return self.project_root / "ventilation" / "ventilation_coefficients.json"

    # --- utilities ---
    def ensure(self, *paths: Path) -> None:
        for p in paths:
            p.parent.mkdir(parents=True, exist_ok=True)

    def write_text(self, path: Path, text: str, encoding: str = "utf-8") -> None:
        self.ensure(path)
        path.write_text(text, encoding=encoding)

    def write_json(self, path: Path, obj, ensure_ascii: bool = False, indent: int = 2) -> None:
        import json
        self.ensure(path)
        path.write_text(json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent), encoding="utf-8")

    def read_json(self, path: Path):
        import json
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    # --- plan helpers ---
    def list_detected_plans(self) -> List[Path]:
        """
        Citește runs/<RUN_ID>/plans_list.json și returnează căile normalizate.
        """
        j = self.read_json(self.plans_list_json()) or {}
        plans = j.get("plans") or []
        return [Path(p).resolve() for p in plans if isinstance(p, str) and p.strip()]

    def has_detected_plans(self) -> bool:
        p = self.plans_list_json()
        if not p.exists():
            return False
        try:
            return len(self.list_detected_plans()) > 0
        except Exception:
            return False

    # --- per plan scratch (pentru rulări paralele/ordonate) ---
    def plan_scratch_dir(self, plan_index: int) -> Path:
        """
        Folder temporar pentru un plan anume, în runs/<RUN_ID>/plans_scratch/pXX
        """
        p = self.run_dir / "plans_scratch" / f"p{plan_index:02d}"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def plan_label(self, plan_index: int) -> str:
        return f"p{plan_index:02d}"

    # --- conveniență pentru sufixelor multi-plan ---
    @staticmethod
    def suffixes(plan_count: int) -> list[str]:
        if plan_count <= 1:
            return [""]
        return [f"_p{i:02d}" for i in range(1, plan_count + 1)]
