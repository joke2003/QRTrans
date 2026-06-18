import pytest
from qrtrans.rs import rs_encode, rs_decode


def test_rs_roundtrip_small():
    data = b"hello colormatrix"
    cw = rs_encode(data, nsym=12)
    assert rs_decode(cw, nsym=12, original_len=len(data)) == data


def test_rs_roundtrip_large_multiblock():
    data = bytes(range(256)) * 40  # 10240B，多块
    cw = rs_encode(data, nsym=12)
    assert rs_decode(cw, nsym=12, original_len=len(data)) == data


def test_rs_corrects_errors_within_capacity():
    data = b"payload to protect" * 5
    cw = bytearray(rs_encode(data, nsym=24))
    # 翻转若干字节（≤nsym/2 个错误可纠）
    for i in (0, 1, 2, 3, 4, 5):
        cw[i] ^= 0xFF
    assert rs_decode(bytes(cw), nsym=24, original_len=len(data)) == data


def test_rs_fails_beyond_capacity():
    from reedsolo import ReedSolomonError
    data = b"x" * 200
    cw = bytearray(rs_encode(data, nsym=10))
    for i in range(20):  # 远超容量
        cw[i] ^= 0xFF
    with pytest.raises(ReedSolomonError):
        rs_decode(bytes(cw), nsym=10, original_len=len(data))
