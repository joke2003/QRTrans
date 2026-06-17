from pathlib import Path
import pytest
from qrtrans.encoder import encode, EncodeOptions
from qrtrans.decoder import decode, DecodeOptions, DecodeResult, DecodeError

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
    with pytest.raises(DecodeError):
        decode(out, tmp_path / "decoded.txt", DecodeOptions(strict=True))

def test_decode_single_image_input(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("hi", encoding="utf-8")
    out = tmp_path / "out"
    encode(src, out, _opts(mode="single"))
    only_png = list(out.glob("*.png"))[0]
    decode(only_png, tmp_path / "decoded.txt", DecodeOptions())
    assert (tmp_path / "decoded.txt").read_text(encoding="utf-8") == "hi"

def test_decode_sha256_tamper_detected(tmp_path):
    from qrtrans.qr_render import render
    from qrtrans.protocol import make_file_payload
    from PIL import Image
    src = tmp_path / "a.txt"
    src.write_text("A" * 100, encoding="utf-8")
    out = tmp_path / "out"
    encode(src, out, _opts(mode="single", batch="tamper01"))
    # 用一个 data 被改、sha256 仍为原值的 payload 覆盖第一张图
    bad_pl = make_file_payload(
        batch="tamper01", fid="f00", relpath="a.txt", fn="a.txt",
        ci=0, tc=1, sha256="0"*64, data_b64="AAAA",
    )
    render(bad_pl, module_px=3, ec="M").save(sorted(out.glob("*.png"))[0], "PNG")
    dest = tmp_path / "dec.txt"
    res = decode(out, dest, DecodeOptions(strict=False))
    assert not dest.exists()
    assert any("sha256" in w for w in res.warnings)

def test_decode_duplicate_chunks_recovered(tmp_path):
    # 输入目录含重复 PNG（同 ci 同 data）应能正常重组
    src = tmp_path / "a.txt"
    src.write_text("hello dup", encoding="utf-8")
    out = tmp_path / "out"
    encode(src, out, _opts(mode="single", batch="dup00001"))
    png = sorted(out.glob("*.png"))[0]
    import shutil
    shutil.copy(png, out / "copy_of_first.png")  # 重复
    decode(out, tmp_path / "dec.txt", DecodeOptions())
    assert (tmp_path / "dec.txt").read_text(encoding="utf-8") == "hello dup"

def test_decode_no_payloads_raises(tmp_path):
    from qrtrans.decoder import DecodeError
    from PIL import Image
    empty = tmp_path / "imgs"
    empty.mkdir()
    # 一张真实但不含 QR 码的空白 PNG
    Image.new("L", (32, 32), 255).save(empty / "x.png", "PNG")
    with pytest.raises(DecodeError):
        decode(empty, tmp_path / "dec.txt", DecodeOptions())
