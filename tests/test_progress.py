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


from qrtrans.encoder import encode, EncodeOptions


def _opts(**over):
    base = dict(mode="array", screen=(1920, 1080), module_px=3, grid="3x1",
                ec="M", chunk_raw_bytes=1300, label=True, batch="prog0001")
    base.update(over)
    return EncodeOptions(**base)


def _capture():
    events = []

    def cb(ev):
        events.append(ev)
    return cb, events


def test_encode_array_emits_prepare_then_frames(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("Z" * 4000)  # 4 块 -> 2 帧（per_frame=3）
    cb, events = _capture()
    encode(src, tmp_path / "out", _opts(mode="array", batch="frame001"), progress=cb)
    assert events[0] == ProgressEvent("prepare", 4, 4)
    frames = [e for e in events if e.phase == "frame"]
    assert [(e.current, e.total) for e in frames] == [(1, 2), (2, 2)]


def test_encode_single_emits_qr_events(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("A" * 5000)  # 4 块
    cb, events = _capture()
    encode(src, tmp_path / "out", _opts(mode="single", batch="qrevt001"), progress=cb)
    assert events[0].phase == "prepare"
    qrs = [e for e in events if e.phase == "qr"]
    assert [(e.current, e.total) for e in qrs] == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_encode_without_progress_still_works(tmp_path):
    # 不传 progress：行为与现状一致（向后兼容）
    src = tmp_path / "a.txt"
    src.write_text("hello")
    res = encode(src, tmp_path / "out", _opts(batch="noprog01"))  # progress 默认 None
    assert res.payload_count >= 1
    assert list((tmp_path / "out").glob("*.png"))


from qrtrans.decoder import decode, DecodeOptions


def test_decode_emits_scan_and_reassemble(tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "b.txt").write_text("B" * 10)
    (root / "top.txt").write_text("T")
    out = tmp_path / "out"
    encode(root, out, _opts(mode="array", batch="dec000001"))
    cb, events = _capture()
    res = decode(out, tmp_path / "dec", DecodeOptions(), progress=cb)
    scans = [e for e in events if e.phase == "scan"]
    reass = [e for e in events if e.phase == "reassemble"]
    assert scans and scans[-1].current == scans[-1].total
    assert reass and reass[-1].current == reass[-1].total
    assert (tmp_path / "dec" / "top.txt").read_text(encoding="utf-8") == "T"


def test_decode_without_progress_still_works(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hi")
    out = tmp_path / "out"
    encode(src, out, _opts(mode="single", batch="dnp00001"))
    decode(out, tmp_path / "dec.txt", DecodeOptions())  # progress 默认 None
    assert (tmp_path / "dec.txt").read_text(encoding="utf-8") == "hi"
