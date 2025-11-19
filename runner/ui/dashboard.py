"""Placeholder pentru un panou Streamlit cu coeficienți."""

from __future__ import annotations

import json
from pathlib import Path

from runner.config.settings import DEFAULT_COEFFICIENTS_FILE


def dump_coefficients(to: Path) -> None:
    data = json.loads(DEFAULT_COEFFICIENTS_FILE.read_text(encoding="utf-8"))
    to.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
