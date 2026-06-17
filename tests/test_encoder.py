from pathlib import Path
import secrets
from qrtrans.encoder import encode, EncodeOptions, EncodeResult
from qrtrans.qr_scan import scan
from qrtrans.protocol import Payload
from PIL import Image

def _opts(**over):
    base = dict(mode="array", screen=(1920, 1080), module_px=3, grid="3x1",
                ec="M", chunk_raw_bytes=1300, label=True, batch="")
    base.update(over)
    return EncodeOptions(**base)

def test_encode_single_file_to_array_frames(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("Hello QRTrans", encoding="utf-8")
    out = tmp_path / "out"
    res = encode(src, out, _opts(mode="array"))
    assert isinstance(res, EncodeResult)
    pngs = list(out.glob("*.png"))
    assert len(pngs) >= 1
    assert all(p.name.startswith("qrtrans_") for p in pngs)
    assert res.batch and len(res.batch) == 8

def test_encode_single_mode_one_png_per_qr(tmp_path):
    src = tmp_path / "big.txt"
    src.write_text("A" * 5000, encoding="utf-8")  # 多块
    out = tmp_path / "out"
    res = encode(src, out, _opts(mode="single"))
    pngs = sorted(out.glob("*.png"))
    assert len(pngs) >= 4   # 5000 字节 / 1300 ≈ 4 块
    assert pngs[0].name.endswith("_0001.png")

def test_encode_directory_preserves_structure_in_payloads(tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "b.txt").write_text("B", encoding="utf-8")
    (root / "empty").mkdir()
    (root / "top.txt").write_text("T", encoding="utf-8")
    out = tmp_path / "out"
    encode(root, out, _opts(mode="array", batch="deadbeef"))
    payloads = []
    for p in sorted(out.glob("*.png")):
        payloads.extend(scan(Image.open(p)))
    paths = sorted(pl.path for pl in payloads)
    assert "sub/b.txt" in paths
    assert "top.txt" in paths
    assert any(pl.type == "dir" and pl.path == "empty/" for pl in payloads)
    assert all(pl.batch == "deadbeef" for pl in payloads)

def test_encode_array_default_3_per_frame(tmp_path):
    src = tmp_path / "big.txt"
    src.write_text("Z" * 4000, encoding="utf-8")  # ~4 块 -> 2 帧
    out = tmp_path / "out"
    encode(src, out, _opts(mode="array", batch="cafef00d"))
    frames = sorted(out.glob("qrtrans_cafef00d_frame_*.png"))
    first = scan(Image.open(frames[0]))
    assert len(first) == 3

def test_encode_auto_grid(tmp_path):
    src = tmp_path / "big.txt"
    src.write_text("Z" * 14000, encoding="utf-8")  # 11 块 -> 5x2=10，首帧满
    out = tmp_path / "out"
    encode(src, out, _opts(mode="array", grid="auto", module_px=2))
    frames = sorted(out.glob("*.png"))
    first = scan(Image.open(frames[0]))
    assert len(first) == 10  # 5x2

def test_encode_empty_input_dir_errors(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    out = tmp_path / "out"
    import pytest
    with pytest.raises(Exception):
        encode(empty, out, _opts())
