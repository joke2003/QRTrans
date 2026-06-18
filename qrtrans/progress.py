from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProgressEvent:
    phase: str       # "prepare" | "frame" | "qr" | "scan" | "reassemble"
    current: int
    total: int


ProgressCallback = Callable[[ProgressEvent], None]
# 契约：
# - 实现在每个工作单元完成后调用；progress 为 None 时不调用。
# - 回调内抛出的异常会向上传播并中止 encode/decode；encode 中途被中止时，
#   已落盘的产物（部分帧/QR PNG）会保留，调用方需自行清理或续传。
# - 建议回调保持轻量且不抛错；如需容错请在回调内自行 try/except。
