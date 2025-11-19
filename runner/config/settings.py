from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

DEFAULT_COEFFICIENTS_FILE = Path(__file__).resolve().parent / "coefficients.json"


def _coerce_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    v = val.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _safe_int(val: Optional[str], default: int) -> int:
    try:
        return int(str(val).strip())
    except Exception:
        return default


@dataclass
class RunnerSettings:
    project_root: Path
    runs_root: Path
    run_id: str
    run_dir: Path
    python_bin: str
    api_url: str = ""
    engine_secret: str = ""
    public_bucket_url: str = ""
    offer_id: str = ""
    plan_count: int = 1
    debug: bool = False

    @classmethod
    def load(cls, project_root: Optional[Path] = None) -> "RunnerSettings":
        prj = project_root or Path(__file__).resolve().parents[2]
        runs_root_env = (os.getenv("RUNS_ROOT") or os.getenv("WORKDIR") or "").strip()
        runs_root = Path(runs_root_env).expanduser().resolve() if runs_root_env else (prj / "runs")

        run_id = (os.getenv("RUN_ID") or "").strip()
        if not run_id:
            import time
            run_id = f"local_{int(time.time())}"

        run_dir = runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        api = (os.getenv("API_URL") or "").strip().rstrip("/")
        secret = (os.getenv("ENGINE_SECRET") or "").strip()
        bucket = (os.getenv("PUBLIC_BUCKET_URL") or "").strip().rstrip("/")
        offer = (os.getenv("OFFER_ID") or "").strip()

        plan_count = _safe_int(os.getenv("PLAN_COUNT"), 1)
        dbg = _coerce_bool(os.getenv("DEBUG"), False)

        venv_bin = prj / ".venv" / ("Scripts" if platform.system() == "Windows" else "bin") / ("python.exe" if platform.system() == "Windows" else "python3")
        python_bin = str(venv_bin) if venv_bin.exists() else "python3"

        return cls(
            project_root=prj,
            runs_root=runs_root,
            run_id=run_id,
            run_dir=run_dir,
            python_bin=python_bin,
            api_url=api,
            engine_secret=secret,
            public_bucket_url=bucket,
            offer_id=offer,
            plan_count=plan_count,
            debug=dbg,
        )

    def env(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "RUN_ID": self.run_id,
                "RUNS_ROOT": str(self.runs_root),
                "WORKDIR": str(self.runs_root),
                "UI_RUN_DIR": self.run_id,
                "PLAN_COUNT": str(self.plan_count),
                "PYTHONUNBUFFERED": "1",
                "PYTHONPATH": self.ensure_pythonpath(),
            }
        )
        if self.api_url:
            env["API_URL"] = self.api_url
        if self.engine_secret:
            env["ENGINE_SECRET"] = self.engine_secret
        if self.public_bucket_url:
            env["PUBLIC_BUCKET_URL"] = self.public_bucket_url
        if self.offer_id:
            env["OFFER_ID"] = self.offer_id
        if extra:
            env.update(extra)
        return env

    def ensure_pythonpath(self) -> str:
        existing = os.getenv("PYTHONPATH") or ""
        prj = str(self.project_root)
        parts = existing.split(os.pathsep) if existing else []
        if prj not in parts:
            parts.insert(0, prj)
        return os.pathsep.join([p for p in parts if p])


def get_openai_api_key() -> str:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing in environment")
    return key


def get_gemini_api_key() -> str:
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing in environment")
    return key


WALL_HEIGHTS_M = {
    "interior_wall": float(os.getenv("WALL_HEIGHT_INTERIOR", "2.6")),
    "exterior_wall": float(os.getenv("WALL_HEIGHT_EXTERIOR", "2.8")),
}
