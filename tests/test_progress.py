from dataclasses import FrozenInstanceError
import pytest
from qrtrans.progress import ProgressEvent, ProgressCallback


def test_progress_event_fields():
    ev = ProgressEvent(phase="frame", current=3, total=10)
    assert ev.phase == "frame"
    assert ev.current == 3
    assert ev.total == 10


def test_progress_event_is_frozen():
    ev = ProgressEvent(phase="qr", current=1, total=2)
    with pytest.raises(FrozenInstanceError):
        ev.current = 5  # type: ignore


def test_progress_callback_is_callable_type():
    # 仅断言 ProgressCallback 可用作类型注解（typing 回调别名）
    events = []
    cb: ProgressCallback = lambda e: events.append(e)
    cb(ProgressEvent("scan", 1, 1))
    assert events == [ProgressEvent("scan", 1, 1)]
