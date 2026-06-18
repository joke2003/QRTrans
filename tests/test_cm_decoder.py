from pathlib import Path
import pytest
from PIL import Image
from qrtrans.cm_encoder import colormatrix_encode, CmEncodeOptions
from qrtrans.cm_decoder import colormatrix_decode, is_colormatrix_frame


def _opts(**over):
    base = dict(colors=16, cell_px=8, ecc_percent=12, compress=True,
                screen=(640, 480), batch="", label=False)
    base.update(over)
    return CmEncodeOptions(**base)


def test_roundtrip_single_file(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("hello colormatrix 你好 🎉")
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="rt000001"))
    dest = tmp_path / "dec.txt"
    colormatrix_decode(out, dest)
    assert dest.read_text(encoding="utf-8") == "hello colormatrix 你好 🎉"


def test_roundtrip_directory(tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "b.txt").write_text("B-content")
    (root / "empty").mkdir()
    (root / "top.txt").write_text("T")
    out = tmp_path / "o"
    colormatrix_encode(root, out, _opts(batch="rt000002"))
    dest = tmp_path / "dec"
    colormatrix_decode(out, dest)
    assert (dest / "sub" / "b.txt").read_text() == "B-content"
    assert (dest / "top.txt").read_text() == "T"
    assert (dest / "empty").is_dir()


def test_roundtrip_multiframe(tmp_path):
    src = tmp_path / "big.txt"; src.write_text("Z" * 20000)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="rt000003", compress=False))  # 关压缩以跨多帧
    dest = tmp_path / "dec.txt"
    colormatrix_decode(out, dest)
    assert dest.read_text() == "Z" * 20000


def test_is_colormatrix_frame_detection(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("x")
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="det00001"))
    p = next(out.glob("*.png"))
    assert is_colormatrix_frame(Image.open(p)) is True
    assert is_colormatrix_frame(Image.new("RGB", (100, 100), "white")) is False
