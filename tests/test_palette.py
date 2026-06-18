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


def test_palette_k4_golden_vector():
    # 调色板属线路格式（解码端必须重现完全相同的颜色），钉死防算法漂移
    assert build_palette(4) == [
        (128, 128, 128), (0, 0, 0), (0, 0, 255), (0, 255, 0),
    ]


def test_palette_k64_golden_vector():
    # 钉死 K=64 完整向量（任何算法/顺序改动都应让此测试失败）
    assert build_palette(64) == [
        (128, 128, 128), (0, 0, 0), (0, 0, 255), (0, 255, 0), (255, 0, 0),
        (0, 255, 255), (255, 0, 255), (255, 255, 0), (255, 255, 255), (0, 64, 128),
        (64, 128, 0), (64, 128, 255), (64, 255, 128), (128, 0, 64), (255, 64, 128),
        (128, 0, 191), (128, 255, 0), (128, 255, 255), (191, 128, 0), (191, 128, 255),
        (191, 255, 128), (0, 128, 64), (0, 191, 191), (64, 64, 64), (255, 128, 64),
        (255, 191, 191), (64, 0, 128), (64, 64, 191), (64, 191, 64), (128, 64, 0),
        (128, 64, 255), (191, 64, 64), (191, 64, 191), (191, 191, 64), (128, 191, 191),
        (191, 0, 128), (0, 0, 64), (0, 0, 128), (0, 64, 0), (0, 64, 64),
        (0, 64, 255), (0, 128, 0), (0, 128, 128), (0, 128, 255), (0, 255, 64),
        (0, 255, 128), (64, 0, 0), (64, 0, 64), (64, 0, 255), (64, 64, 0),
        (64, 64, 255), (64, 128, 128), (64, 191, 191), (64, 255, 0), (64, 255, 64),
        (64, 255, 255), (128, 0, 0), (128, 0, 255), (128, 64, 128), (128, 128, 64),
        (128, 191, 0), (128, 191, 255), (128, 255, 64), (128, 255, 191),
    ]
