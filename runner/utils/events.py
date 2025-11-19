from __future__ import annotations

from typing import Iterable

try:
    from net_bridge import post_event
except Exception:  # pragma: no cover
    post_event = None  # type: ignore


def emit_event(message: str, files: Iterable[dict] | None = None) -> None:
    if not post_event:
        return
    try:
        post_event(message, files=list(files or []))
    except Exception:
        pass
