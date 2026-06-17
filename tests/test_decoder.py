from pathlib import Path
import pytest
from qrtrans.encoder import encode, EncodeOptions
from qrtrans.decoder import decode, DecodeOptions, DecodeResult

def _opts(**over):
    base = dict(mode="array", screen=(1920, 1080), module_px=3, grid="3x1",
                ec="M", chunk_raw_bytes=1300, label=True, batch="deadbeef")
    base.update(over)
    return EncodeOptions(**base)

def test_decode_roundtrip_single_file(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("Hello QRTrans", encoding="utf-8")
    out = tmp_path / "out"
    encode(src, out, _opts())
    res = decode(out, tmp_path / "decoded.txt", DecodeOptions(strict=False))
    assert (tmp_path / "decoded.txt").read_text(encoding="utf-8") == "Hello QRTrans"
    assert res.warnings == []

def test_decode_roundtrip_directory(tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "b.txt").write_text("B-content", encoding="utf-8")
    (root / "empty").mkdir()
    (root / "top.txt").write_text("T-content", encoding="utf-8")
    out = tmp_path / "out"
    encode(root, out, _opts())
    dest = tmp_path / "decoded"
    res = decode(out, dest, DecodeOptions(strict=False))
    assert (dest / "sub" / "b.txt").read_text(encoding="utf-8") == "B-content"
    assert (dest / "top.txt").read_text(encoding="utf-8") == "T-content"
    assert (dest / "empty").is_dir()
    assert res.warnings == []

def test_decode_long_file_multi_chunk(tmp_path):
    src = tmp_path / "big.txt"
    content = "Q" * 5000
    src.write_text(content, encoding="utf-8")
    out = tmp_path / "out"
    encode(src, out, _opts())
    res = decode(out, tmp_path / "decoded.txt", DecodeOptions())
    assert (tmp_path / "decoded.txt").read_text(encoding="utf-8") == content

def test_decode_unicode_content(tmp_path):
    src = tmp_path / "cn.txt"
    content = "你好，世界！🎉 unicode 测试"
    src.write_text(content, encoding="utf-8")
    out = tmp_path / "out"
    encode(src, out, _opts())
    decode(out, tmp_path / "decoded.txt", DecodeOptions())
    assert (tmp_path / "decoded.txt").read_text(encoding="utf-8") == content

def test_decode_missing_chunk_warns_and_recovers_others(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("A" * 3000, encoding="utf-8")  # 多块
    (root / "b.txt").write_text("B", encoding="utf-8")
    out = tmp_path / "out"
    encode(root, out, _opts(mode="single"))   # 单 QR/文件便于删一块
    pngs = sorted(out.glob("*.png"))
    pngs[0].unlink()  # 删掉第一块
    dest = tmp_path / "decoded"
    res = decode(out, dest, DecodeOptions(strict=False))
    assert (dest / "b.txt").read_text(encoding="utf-8") == "B"
    assert res.warnings  # 有告警
    assert any("a.txt" in w for w in res.warnings)

def test_decode_missing_chunk_strict_fails(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("A" * 3000, encoding="utf-8")
    out = tmp_path / "out"
    encode(src, out, _opts(mode="single"))
    pngs = sorted(out.glob("*.png"))
    pngs[0].unlink()
    with pytest.raises(Exception):
        decode(out, tmp_path / "decoded.txt", DecodeOptions(strict=True))

def test_decode_single_image_input(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("hi", encoding="utf-8")
    out = tmp_path / "out"
    encode(src, out, _opts(mode="single"))
    only_png = list(out.glob("*.png"))[0]
    decode(only_png, tmp_path / "decoded.txt", DecodeOptions())
    assert (tmp_path / "decoded.txt").read_text(encoding="utf-8") == "hi"
