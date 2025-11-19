from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineStep:
    name: str
    script: str
    stage_key: str
    description: str
    parallel: bool = True
