import pytest
from qrtrans.palette import build_palette, nearest, COLOR_BITS


@pytest.mark.parametrize("k", [4, 8, 16, 32, 64])
def test_palette_size_and_unique(k):
    p = build_palette(k)
    assert len(p) == k
    assert len(set(p)) == k
    for c in p:
        assert len(c) == 3 and all(0 <= v <= 255 for v in c)


def test_palette_deterministic():
    assert build_palette(16) == build_palette(16)


def test_nearest_exact():
    p = build_palette(16)
    for i, c in enumerate(p):
        assert nearest(p, c) == i


def test_nearest_closest():
    p = build_palette(4)
    assert nearest(p, (p[0][0] + 1, p[0][1], p[0][2])) == 0


def test_color_bits_table():
    assert COLOR_BITS == {4: 2, 8: 3, 16: 4, 32: 5, 64: 6}


def test_invalid_k_rejected():
    with pytest.raises(ValueError):
        build_palette(10)
