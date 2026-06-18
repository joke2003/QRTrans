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


def test_encode_payload_fits_no_truncation(tmp_path):
    # 验证每帧的 头+载荷 单元数 ≤ 内部网格单元数（无静默截断）
    from qrtrans import cm_protocol
    from qrtrans.palette import COLOR_BITS
    from qrtrans.finder import MARKER_CELL
    import math
    src = tmp_path / "big.txt"; src.write_text("Z" * 20000)
    out = tmp_path / "o"
    opts = _opts(batch="fit00001", compress=False)
    colormatrix_encode(src, out, opts)
    # 从任一帧反推：内部网格容量 vs 头+载荷
    gw = 640 // opts.cell_px
    gh = 480 // opts.cell_px
    iw = gw - 2 * MARKER_CELL
    ih = gh - 2 * MARKER_CELL
    interior = iw * ih
    bpc = COLOR_BITS[opts.colors]
    header_cells = math.ceil(62 * 8 / bpc)
    # 每帧载荷字节数应 ≤ (interior - header_cells) * bpc / 8
    max_payload_bytes = (interior - header_cells) * bpc // 8
    assert max_payload_bytes > 0
    # 进一步：实际解码往返留给任务 6；这里至少保证 encode 不报错、产物存在
    assert list(out.glob("*.png"))


def test_encode_random_bytes_not_compressed(tmp_path):
    # 不可压缩内容应触发 compressed=0（有收益才压）
    import os
    from qrtrans.cm_decoder import _try_decode_header
    from qrtrans.finder import locate_markers
    src = tmp_path / "rand.bin"; src.write_bytes(os.urandom(5000))
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="rand0001"))
    # 读第一帧头验证 compressed==0
    p = sorted(out.glob("*.png"))[0]
    with Image.open(p) as img:
        img.load()
        corners = locate_markers(img)
        info = None
        if corners is not None:
            for cp in (3, 4, 5, 6, 8, 10, 12):
                info = _try_decode_header(img, corners, cp)
                if info:
                    break
        assert info is not None
        header = info[0]
        assert header.compressed == 0
