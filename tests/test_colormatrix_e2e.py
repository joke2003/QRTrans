from pathlib import Path
import pytest
from qrtrans.cm_encoder import colormatrix_encode, CmEncodeOptions
from qrtrans.cm_decoder import colormatrix_decode


def _opts(**over):
    base = dict(colors=16, cell_px=8, ecc_percent=12, compress=True,
                screen=(640, 480), batch="", label=False, margin=0)
    base.update(over)
    return CmEncodeOptions(**base)


def _rt(tmp_path, mode_opts, content_fn):
    src = tmp_path / "a.bin"
    src.write_bytes(content_fn())
    out = tmp_path / "o"
    dec = tmp_path / "dec"
    colormatrix_encode(src, out, _opts(batch="e2000001", **mode_opts))
    colormatrix_decode(out, dec)
    return dec.read_bytes()


def test_e2e_unicode_emoji(tmp_path):
    assert _rt(tmp_path, {}, lambda: "你好 🎉 cm".encode()) == "你好 🎉 cm".encode()


def test_e2e_binary(tmp_path):
    assert _rt(tmp_path, {}, lambda: bytes(range(256)) * 4) == bytes(range(256)) * 4


def test_e2e_no_compress(tmp_path):
    assert _rt(tmp_path, {"compress": False}, lambda: b"x" * 5000) == b"x" * 5000


def test_e2e_colors32_cellpx3(tmp_path):
    assert _rt(tmp_path, {"colors": 32, "cell_px": 3}, lambda: b"y" * 3000) == b"y" * 3000


def test_e2e_directory_with_empty(tmp_path):
    root = tmp_path / "src"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "b.txt").write_bytes(b"B-content")
    (root / "empty").mkdir()
    (root / "top.txt").write_bytes(b"T")
    out = tmp_path / "o"
    colormatrix_encode(root, out, _opts(batch="e2dir001"))
    dest = tmp_path / "dec"
    colormatrix_decode(out, dest)
    assert (dest / "sub" / "b.txt").read_bytes() == b"B-content"
    assert (dest / "top.txt").read_bytes() == b"T"
    assert (dest / "empty").is_dir()


def test_e2e_drop_frame_fails(tmp_path):
    # 丢一帧 → 缺帧报错（与 QR 一致；v1 每帧独立 RS，无跨帧擦除还原）
    src = tmp_path / "a.txt"
    src.write_text("Z" * 20000)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="e2drop01", compress=False))
    pngs = sorted(out.glob("*.png"))
    pngs[0].unlink()
    with pytest.raises(ValueError, match="missing frames"):
        colormatrix_decode(out, tmp_path / "dec")


def test_e2e_default_params_on_full_screen(tmp_path):
    # 默认参数（16色/4px）在 1920x1080 下往返
    src = tmp_path / "a.txt"
    src.write_text("full screen default " * 200)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="e2full01", colors=16, cell_px=4,
                                       screen=(1920, 1080)))
    dest = tmp_path / "dec.txt"
    colormatrix_decode(out, dest)
    assert dest.read_text() == "full screen default " * 200


def test_e2e_large_screen_2560x1440(tmp_path):
    # 回归：宽图下 locate_markers 的粗采样质心偏移，曾导致 header 解不出、整帧被丢、
    # colormatrix_decode 报 "no colormatrix frames found"。1920x1080 因 step 不同侥幸能过。
    src = tmp_path / "a.txt"
    src.write_text("big screen 2560 " * 500)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="e2big2561", colors=16, cell_px=4,
                                       screen=(2560, 1440)))
    dest = tmp_path / "dec.txt"
    colormatrix_decode(out, dest)
    assert dest.read_text() == "big screen 2560 " * 500


def test_e2e_2560_label_margin_roundtrip(tmp_path):
    # 回归 Win11 实测 bug：2560 宽 + label(+旧无 margin) 时帧=screen+40，
    # viewer 全屏裁掉顶部 marker，摄像头/截图无法解码。现 label+margin 下帧==screen。
    src = tmp_path / "a.txt"
    src.write_text("wide margin label " * 500)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="e2wlm0001", colors=16, cell_px=4,
                                       screen=(2560, 1440), label=True, margin=24))
    # 帧严格 == screen（不被裁切）
    from PIL import Image
    p = sorted(out.glob("*.png"))[0]
    with Image.open(p) as im:
        assert im.size == (2560, 1440)
    dest = tmp_path / "dec.txt"
    colormatrix_decode(out, dest)
    assert dest.read_text() == "wide margin label " * 500
