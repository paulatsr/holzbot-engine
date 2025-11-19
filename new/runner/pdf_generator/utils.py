# new/runner/pdf_generator/utils.py
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime


def format_money(value: float | int | None, currency: str = "EUR") -> str:
    """Formatează valori monetare: 1234.56 → 1.234,56 EUR"""
    if value is None:
        return "—"
    try:
        v = float(value)
        # Formatare germană: . pentru mii, , pentru zecimale
        formatted = f"{v:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
        return f"{formatted} {currency}"
    except Exception:
        return "—"


def format_area(value: float | int | None) -> str:
    """Formatează arii: 123.45 → 123,45 m²"""
    if value is None:
        return "—"
    try:
        v = float(value)
        return f"{v:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " m²"
    except Exception:
        return "—"


def format_length(value: float | int | None) -> str:
    """Formatează lungimi: 12.34 → 12,34 m"""
    if value is None:
        return "—"
    try:
        v = float(value)
        return f"{v:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " m"
    except Exception:
        return "—"


def safe_get(data: dict, *keys, default=None):
    """Safe nested dict access"""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def load_json_safe(path: Path) -> dict:
    """Load JSON with error handling"""
    if not path or not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_plan_image_path(plan_id: str, base_dir: Path) -> Path | None:
    """
    Caută imaginea pentru un plan specific:
    - base_dir/plan_id/plan.jpg
    - base_dir/classified/blueprints/plan_id.jpg
    """
    candidates = [
        base_dir / plan_id / "plan.jpg",
        base_dir / "classified" / "blueprints" / f"{plan_id}.jpg",
        base_dir / "segmentation" / "classified" / "blueprints" / f"{plan_id}.jpg",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    return None