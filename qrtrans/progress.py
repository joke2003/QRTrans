from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProgressEvent:
    phase: str       # "prepare" | "frame" | "qr" | "scan" | "reassemble"
    current: int
    total: int


ProgressCallback = Callable[[ProgressEvent], None]
