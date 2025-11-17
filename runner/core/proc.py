#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
core/proc.py
------------
Utilitare comune pentru rulări în pipeline:
- _banner(msg): separator vizual frumos în STDOUT
- run_step(...): rulează o funcție "pas" cu logging + cod retur
- sh(cmd): execuție simplă de comenzi shell cu output live
- tee_write(path, text): adaugă text într-un fișier-log, creând directoare
"""

from __future__ import annotations

import os
import sys
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence


def _banner(msg: str, width: int = 80, char: str = "═") -> str:
    line = (char * max(0, width - 2))
    return f"\n╔{line}╗\n║ {msg}\n╚{line}╝\n"


def tee_write(path: Path | str, text: str, ensure_newline: bool = True) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(text + ("\n" if ensure_newline and not text.endswith("\n") else ""))


def sh(cmd: str | Sequence[str], cwd: Optional[Path | str] = None, env: Optional[dict] = None) -> int:
    """
    Rulează o comandă shell/exec, stream-uind output-ul.
    Returnează codul de ieșire.
    """
    if isinstance(cmd, str):
        args = shlex.split(cmd)
    else:
        args = list(cmd)

    proc = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        env=env or os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    proc.wait()
    return int(proc.returncode or 0)


@dataclass
class StepResult:
    name: str
    code: int
    message: str = ""


def run_step(name: str, fn: Callable[[], int], on_error: Optional[Callable[[int], None]] = None) -> StepResult:
    """
    Rulează o funcție-„pas” (care întoarce cod int) și loghează frumos.
    """
    print(_banner(f"▶️  STEP: {name}"))
    try:
        code = int(fn())
    except SystemExit as e:
        code = int(e.code or 1)
    except Exception as e:
        code = 1
        print(f"❌ Eroare neașteptată în pasul '{name}': {e}", flush=True)

    if code == 0:
        print(f"✅ Pas '{name}' finalizat cu succes.\n", flush=True)
        return StepResult(name=name, code=0)
    else:
        print(f"❌ Pas '{name}' a eșuat cu code={code}.\n", flush=True)
        if on_error:
            try:
                on_error(code)
            except Exception as e:
                print(f"⚠️ on_error a aruncat excepție: {e}", flush=True)
        return StepResult(name=name, code=code)
