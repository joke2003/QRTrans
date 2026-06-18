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


@pytest.mark.parametrize("colors", [4, 16, 64])
@pytest.mark.parametrize("cell_px", [4, 8, 10])
def test_roundtrip_parametrized(tmp_path, colors, cell_px):
    src = tmp_path / "a.txt"; src.write_text("param 你好 " + "x" * 500)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(colors=colors, cell_px=cell_px, batch=f"p{colors}{cell_px}"))
    dest = tmp_path / "dec.txt"
    colormatrix_decode(out, dest)
    assert dest.read_text(encoding="utf-8").startswith("param 你好")


def test_decode_missing_frame_raises(tmp_path):
    src = tmp_path / "big.txt"; src.write_text("Z" * 20000)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="miss0001", compress=False))
    pngs = sorted(out.glob("*.png")); pngs[0].unlink()
    with pytest.raises(ValueError, match="missing frames"):
        colormatrix_decode(out, tmp_path / "dec.txt")


def test_decode_rs_corrects_minor_damage(tmp_path):
    from PIL import Image, ImageDraw
    src = tmp_path / "a.txt"; src.write_text("RS correct me " * 20)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="rsdm0001"))
    p = sorted(out.glob("*.png"))[0]
    img = Image.open(p).convert("RGB"); img.load()
    d = ImageDraw.Draw(img)
    d.rectangle([100, 100, 104, 104], fill=(200, 50, 50))   # 5×5，控制在 RS 容量内
    img.save(p, "PNG")
    dest = tmp_path / "dec.txt"
    colormatrix_decode(out, dest)
    assert dest.read_text(encoding="utf-8").startswith("RS correct me")


def test_decode_rejects_inconsistent_batch(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("batch A")
    out1 = tmp_path / "o1"; out2 = tmp_path / "o2"
    colormatrix_encode(src, out1, _opts(batch="aaaaaaaa"))
    colormatrix_encode(src, out2, _opts(batch="bbbbbbbb"))
    import shutil
    mixed = tmp_path / "mix"; mixed.mkdir()
    for p in list(out1.glob("*.png")) + list(out2.glob("*.png")):
        shutil.copy(p, mixed)
    with pytest.raises(ValueError, match="inconsistent"):
        colormatrix_decode(mixed, tmp_path / "dec.txt")
