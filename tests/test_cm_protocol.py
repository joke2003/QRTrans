import pytest
from qrtrans.cm_protocol import (
    CmHeader, CM_MAGIC, header_to_bytes, header_from_bytes,
    bytes_to_indices, indices_to_bytes, COLOR_BITS_LOOKUP,
)
from qrtrans.palette import COLOR_BITS


def _hdr(**over):
    base = dict(magic=CM_MAGIC, version=1, palette_version=1, k=16, cell_px=4,
                grid_w=100, grid_h=80, batch="deadbeef", frame_index=2, frame_total=5,
                ecc_percent=12, compressed=1, payload_len=1234, payload_sha256="a"*64)
    base.update(over)
    return CmHeader(**base)


def test_header_roundtrip():
    h = _hdr()
    b = header_to_bytes(h)
    assert header_from_bytes(b) == h


def test_header_bad_magic_rejected():
    b = bytearray(header_to_bytes(_hdr()))
    b[0:4] = b"XXXX"
    with pytest.raises(ValueError):
        header_from_bytes(bytes(b))


def test_header_crc_corruption_rejected():
    b = bytearray(header_to_bytes(_hdr()))
    b[10] ^= 0xFF  # 改一字段字节
    with pytest.raises(ValueError):
        header_from_bytes(bytes(b))


def test_index_bitpack_roundtrip():
    data = bytes(range(256))
    bpc = COLOR_BITS[16]
    idx = bytes_to_indices(data, bpc)
    assert indices_to_bytes(idx, bpc, original_len=len(data)) == data


def test_index_bitpack_multibyte_cells():
    data = b"abc"
    bpc = COLOR_BITS[4]
    idx = bytes_to_indices(data, bpc)
    assert indices_to_bytes(idx, bpc, original_len=len(data)) == data


def test_index_bitpack_padding_bpc3():
    # bpc=3（K=8）：8 不被 3 整除 → 触发补零 padding 分支
    from qrtrans.palette import COLOR_BITS
    data = b"\xff\x01\x02\x03"  # 32 bit / bpc=3 → 需补到 33 bit，11 个索引
    bpc = COLOR_BITS[8]
    idx = bytes_to_indices(data, bpc)
    assert len(idx) == 11   # ceil(32/3)
    assert indices_to_bytes(idx, bpc, original_len=len(data)) == data


def test_index_bitpack_padding_bpc5_bpc6():
    from qrtrans.palette import COLOR_BITS
    for k in (32, 64):
        bpc = COLOR_BITS[k]
        data = bytes(range(7))  # 56 bit，bpc=5/6 均不整除
        idx = bytes_to_indices(data, bpc)
        assert indices_to_bytes(idx, bpc, original_len=len(data)) == data


def test_index_bitpack_empty():
    assert bytes_to_indices(b"", 4) == []
    assert indices_to_bytes([], 4, original_len=0) == b""


def test_index_bitpack_zero_original_len():
    # 有索引但 original_len=0 → 返回空
    idx = [0, 1, 2, 3]
    assert indices_to_bytes(idx, 4, original_len=0) == b""
