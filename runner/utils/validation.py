from __future__ import annotations

from pathlib import Path


def ensure_exists(path: Path, description: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Lipsește {description}: {path}")
    return path


def require_positive(value: float, label: str) -> float:
    if value <= 0:
        raise ValueError(f"{label} trebuie să fie pozitiv (got {value})")
    return value
