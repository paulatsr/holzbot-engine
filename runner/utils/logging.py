from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

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


def log(msg: str, level: str = "INFO") -> None:
    sys.stdout.write(f"[{_ts()}] [RUNNER] [{level}] {msg}\n")
    sys.stdout.flush()


def warn(msg: str) -> None:
    log(f"⚠️  {msg}", level="WARN")


def error(msg: str) -> None:
    log(f"❌ {msg}", level="ERR")


def begin_stage(key: str, title: str, hint: str = "") -> None:
    if _UI_OK and _begin_stage:
        try:
            _begin_stage(key, title=title, plan_hint=hint)
        except Exception:
            pass
    log(f"== BEGIN {key}: {title}")


def finalize_stage(key: str) -> None:
    if _UI_OK and _finalize_stage:
        try:
            _finalize_stage(key)
        except Exception:
            pass
    log(f"== END {key}")


def emit(stage: str, text: str = "", image: Optional[Path] = None) -> None:
    if _UI_OK and text and _record_text:
        try:
            _record_text(text, stage=stage, filename="_live.txt", append=True)
        except Exception:
            pass
    if _UI_OK and image and _record_image and image.exists():
        try:
            _record_image(str(image), stage=stage)
        except Exception:
            pass
