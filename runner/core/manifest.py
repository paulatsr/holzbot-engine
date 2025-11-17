# engine/runner/core/manifest.py
# -*- coding: utf-8 -*-

from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
import json
from typing import List, Dict, Any

DEFAULT_MANIFEST_NAME = "plans_list.json"


@dataclass
class PlansManifest:
    generated_at: str
    plan_count: int
    plans: List[str]

    @staticmethod
    def now(plans: List[str]) -> "PlansManifest":
        abs_plans = [str(Path(p).resolve()) for p in plans]
        return PlansManifest(
            generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            plan_count=len(abs_plans),
            plans=abs_plans,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ------------- helpers -------------
def manifest_path(runs_root: Path | str, run_id: str, name: str = DEFAULT_MANIFEST_NAME) -> Path:
    """
    Returnează calea la runs/<RUN_ID>/plans_list.json (sau <name> custom).
    Creează directorul dacă lipsește.
    """
    rr = Path(runs_root) if runs_root else Path("./runs")
    p = rr / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p / name


def is_valid_manifest(obj: Dict[str, Any]) -> bool:
    """
    Validare minimalistă (fără dependențe externe):
      - generated_at: string ISO-ish
      - plan_count: int >= 0
      - plans: list[str] cu fișiere existente (nu forțăm existența; doar formă)
    """
    try:
        if not isinstance(obj, dict):
            return False
        if not isinstance(obj.get("generated_at", ""), str):
            return False
        if not isinstance(obj.get("plan_count", -1), int):
            return False
        plans = obj.get("plans", [])
        if not isinstance(plans, list):
            return False
        if not all(isinstance(x, str) for x in plans):
            return False
        return True
    except Exception:
        return False


def load_manifest(path: Path | str) -> PlansManifest | None:
    """
    Citește manifestul; dacă nu e valid, întoarce None.
    Normalizează căile la absolut.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not is_valid_manifest(data):
        return None

    plans_abs = [str(Path(x).resolve()) for x in (data.get("plans") or [])]
    return PlansManifest(
        generated_at=str(data.get("generated_at")),
        plan_count=int(data.get("plan_count") or len(plans_abs)),
        plans=plans_abs,
    )


def write_manifest(path: Path | str, plans: List[str]) -> PlansManifest:
    """
    Scrie manifestul la disc (cu indent 2, UTF-8).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    man = PlansManifest.now(plans)
    p.write_text(json.dumps(man.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return man


def ensure_manifest(runs_root: Path | str, run_id: str, plans: List[str]) -> Path:
    """
    Shortcut: construiește calea + scrie manifestul.
    Returnează calea finală.
    """
    mp = manifest_path(runs_root, run_id)
    write_manifest(mp, plans)
    return mp
