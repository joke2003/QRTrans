from PIL import Image
from qrtrans.encoder import encode, EncodeOptions
from qrtrans.decoder import decode, DecodeOptions


def _opts(**over):
    base = dict(mode="array", screen=(1920, 1080), module_px=3, grid="3x1",
                ec="M", chunk_raw_bytes=1300, label=True, batch="e2e00001")
    base.update(over)
    return EncodeOptions(**base)


def _roundtrip_dir(tmp_path, mode, grid="3x1", module_px=3):
    root = tmp_path / "src"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "guide.md").write_text("# 中文标题 🎉\n\n正文 " + "x" * 2000, encoding="utf-8")
    (root / "notes.txt").write_text("short", encoding="utf-8")
    (root / "empty").mkdir()
    out = tmp_path / "out"
    encode(root, out, _opts(mode=mode, grid=grid, module_px=module_px))
    dest = tmp_path / "decoded"
    res = decode(out, dest, DecodeOptions(strict=False))
    assert res.warnings == []
    assert (dest / "docs" / "guide.md").read_text(encoding="utf-8").startswith("# 中文标题 🎉")
    assert (dest / "notes.txt").read_text(encoding="utf-8") == "short"
    assert (dest / "empty").is_dir()


def test_e2e_array_mode(tmp_path):
    _roundtrip_dir(tmp_path, "array")

def test_e2e_single_mode(tmp_path):
    _roundtrip_dir(tmp_path, "single")

def test_e2e_aggressive_5x2_2px(tmp_path):
    _roundtrip_dir(tmp_path, "array", grid="5x2", module_px=2)

def test_e2e_auto_grid(tmp_path):
    _roundtrip_dir(tmp_path, "array", grid="auto")

def test_e2e_label_off(tmp_path):
    root = tmp_path / "src2"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")
    out = tmp_path / "out2"
    encode(root, out, _opts(mode="array", label=False, batch="nolabel1"))
    # 首帧高度应等于 cell_px（无横幅）
    from qrtrans.qr_render import CELL_MODULES
    first = Image.open(sorted(out.glob("*.png"))[0])
    assert first.size[1] == CELL_MODULES * 3

def test_e2e_no_label_still_decodes(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "a.txt").write_text("data " * 500, encoding="utf-8")
    out = tmp_path / "out"
    encode(root, out, _opts(mode="array", label=False, batch="nl2"))
    dest = tmp_path / "dec"
    # 单文件无目录标记 → 解码器按单文件模式把内容直接写到 output（见 decoder.py single_file_mode）
    decode(out, dest, DecodeOptions())
    assert dest.read_text(encoding="utf-8") == "data " * 500

def test_e2e_corrupted_chunk_detected(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "a.txt").write_text("A" * 3000, encoding="utf-8")
    out = tmp_path / "out"
    encode(root, out, _opts(mode="single", batch="corrupt1"))
    # 篡改某张图：重新生成一张内容不同的 QR 覆盖
    from qrtrans.qr_render import render
    from qrtrans.protocol import make_file_payload
    bad_pl = make_file_payload(
        batch="corrupt1", fid="f00", relpath="a.txt", fn="a.txt",
        ci=0, tc=3, sha256="0"*64, data_b64="AAAA",
    )
    render(bad_pl, module_px=3, ec="M").save(sorted(out.glob("*.png"))[0], "PNG")
    dest = tmp_path / "dec"
    res = decode(out, dest, DecodeOptions(strict=False))
    assert any("a.txt" in w for w in res.warnings)
    assert not (dest / "a.txt").exists()
