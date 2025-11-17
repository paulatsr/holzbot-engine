#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
core/logging.py
----------------
Inițializare logging uniform pentru întreg workflow-ul.

Expune:
  - setup_logging(settings: Settings, log_file: Optional[Path] = None) -> logging.Logger
  - get_logger(name: str | None = None) -> logging.Logger
  - trace(msg: str)  # helper scurt cu timestamp + RUN_ID

Folosește format prietenos pentru terminal și scrie, dacă e dorit, și într-un fișier
(runs/<RUN_ID>/engine.log).
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import colorama  # type: ignore
    colorama.just_fix_windows_console()
    _HAVE_COLOR = True
except Exception:
    _HAVE_COLOR = False

# ANSI culori simple
class _C:
    if _HAVE_COLOR:
        GRAY = "\033[90m"
        RED = "\033[91m"
        YELLOW = "\033[93m"
        GREEN = "\033[92m"
        CYAN = "\033[96m"
        RESET = "\033[0m"
    else:
        GRAY = RED = YELLOW = GREEN = CYAN = RESET = ""


_RUN_ID_CACHE = os.getenv("RUN_ID", "")


def _level_to_color(level: int) -> str:
    if level >= logging.ERROR:
        return _C.RED
    if level >= logging.WARNING:
        return _C.YELLOW
    if level >= logging.INFO:
        return _C.GREEN
    return _C.GRAY


class _ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        run = _RUN_ID_CACHE or os.getenv("RUN_ID", "")
        lvl = record.levelname
        color = _level_to_color(record.levelno)
        name = record.name
        msg = super().format(record)
        prefix = f"[{ts}]"
        if run:
            prefix += f" [{run}]"
        prefix += f" [{name}]"
        return f"{_C.CYAN}{prefix}{_C.RESET} {color}{lvl:>7}{_C.RESET} {msg}"


def setup_logging(settings, log_file: Optional[Path] = None) -> logging.Logger:
    """
    Configurează root logger:
      - handler consolă color
      - handler fișier (runs/<RUN_ID>/engine.log) dacă e posibil
    """
    global _RUN_ID_CACHE
    _RUN_ID_CACHE = getattr(settings, "run_id", os.getenv("RUN_ID", "")) or _RUN_ID_CACHE

    root = logging.getLogger()
    # evita dublarea handlerelor dacă este apelat de mai multe ori
    if getattr(root, "_engine_initialized", False):
        return root

    root.setLevel(getattr(logging, getattr(settings, "log_level", "INFO"), logging.INFO))

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(root.level)
    ch.setFormatter(_ConsoleFormatter("%(message)s"))
    root.addHandler(ch)

    # File
    try:
        lf = log_file or (settings.run_dir / "engine.log")
        lf.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(lf), encoding="utf-8")
        fh.setLevel(root.level)
        fh.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S"
        ))
        root.addHandler(fh)
    except Exception as e:
        root.warning(f"Nu pot inițializa file logger: {e}")

    root._engine_initialized = True  # type: ignore[attr-defined]
    return root


def get_logger(name: Optional[str] = None) -> logging.Logger:
    return logging.getLogger(name or "engine")


def trace(msg: str, logger: Optional[logging.Logger] = None):
    """
    Shortcut pentru mesaje stil „trace” (INFO cu prefix consistent).
    """
    log = logger or get_logger("trace")
    log.info(msg)
