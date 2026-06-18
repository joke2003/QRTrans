from pathlib import Path
from PIL import Image
from qrtrans.cm_encoder import colormatrix_encode, CmEncodeOptions
from qrtrans.cm_decoder import is_colormatrix_frame


def _opts(**over):
    base = dict(colors=16, cell_px=8, ecc_percent=12, compress=True,
                screen=(640, 480), batch="", label=False)
    base.update(over)
    return CmEncodeOptions(**base)


def test_encode_produces_frames(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("hello colormatrix")
    out = tmp_path / "o"
    res = colormatrix_encode(src, out, _opts(batch="enc00001"))
    pngs = list(out.glob("*.png"))
    assert pngs
    for p in pngs:
        assert is_colormatrix_frame(Image.open(p)) is True


def test_encode_multiframe_for_large(tmp_path):
    src = tmp_path / "big.txt"; src.write_text("Z" * 20000)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="enc00002", compress=False))
    assert len(list(out.glob("*.png"))) >= 2


def test_encode_auto_compress_text(tmp_path):
    src = tmp_path / "t.txt"; src.write_text("A" * 5000)  # 高度可压缩
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="enc00003"))
    assert list(out.glob("*.png"))
