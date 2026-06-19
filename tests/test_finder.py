import pytest
from PIL import Image, ImageDraw
from qrtrans.finder import draw_markers, locate_markers, interior_box, MARKER_COLOR, MARKER_CELL


def test_draw_then_locate_four_corners():
    img = Image.new("RGB", (200, 150), "white")
    draw_markers(img, cell_px=4)
    corners = locate_markers(img)
    assert corners is not None and len(corners) == 4
    xs = sorted(c[0] for c in corners)
    ys = sorted(c[1] for c in corners)
    assert xs[0] < xs[-1] and ys[0] < ys[-1]


def test_locate_returns_none_when_absent():
    img = Image.new("RGB", (200, 150), "white")
    assert locate_markers(img) is None


def test_locate_with_interior_black_cells():
    # 关键回归：内部含大量黑色块（模拟真实帧的黑色单元格），标记色不应被混淆
    img = Image.new("RGB", (400, 300), "white")
    d = ImageDraw.Draw(img)
    for x in range(50, 380, 18):
        for y in range(50, 280, 18):
            d.rectangle([x, y, x + 14, y + 14], fill=(0, 0, 0))
    draw_markers(img, cell_px=8)   # 角标记画在最外角（覆盖部分内部黑块位置没关系）
    corners = locate_markers(img)
    assert corners is not None and len(corners) == 4
    TL = corners[0]
    # TL 必须在左上角附近、不被内部黑块拉偏
    assert TL[0] < 40 and TL[1] < 40


def test_locate_precision():
    img = Image.new("RGB", (400, 300), "white")
    draw_markers(img, cell_px=8)
    tl, tr, bl, br = locate_markers(img)
    half = (MARKER_CELL * 8) // 2
    assert abs(tl[0] - half) <= 4 and abs(tl[1] - half) <= 4
    assert abs(tr[0] - (400 - 1 - half)) <= 6 and abs(tr[1] - half) <= 4
    assert abs(bl[0] - half) <= 4 and abs(bl[1] - (300 - 1 - half)) <= 6
    assert abs(br[0] - (400 - 1 - half)) <= 6 and abs(br[1] - (300 - 1 - half)) <= 6


def test_interior_box_inside_and_uses_all_corners():
    img = Image.new("RGB", (400, 300), "white")
    draw_markers(img, cell_px=8)
    corners = locate_markers(img)
    x0, y0, x1, y1 = interior_box(corners, cell_px=8)
    assert 0 < x0 < x1 < 400 and 0 < y0 < y1 < 300


@pytest.mark.parametrize("scale", [0.85, 0.95, 1.05, 1.15])
def test_locate_survives_scales(scale):
    img = Image.new("RGB", (400, 300), "white")
    draw_markers(img, cell_px=8)
    scaled = img.resize((int(400 * scale), int(300 * scale)), Image.BILINEAR)
    corners = locate_markers(scaled)
    assert corners is not None and len(corners) == 4


def test_locate_precision_large_image():
    # 回归：2560 宽图下 step=min(W,H)//200=7，粗采样质心曾偏移 >2px
    # （marker 12px、采样 {0,7}→质心 3，真中心 5.5），是 cm 大屏解码失败的根因。
    W, H = 2560, 1440
    img = Image.new("RGB", (W, H), "white")
    draw_markers(img, cell_px=4)
    tl, tr, bl, br = locate_markers(img)
    half = (MARKER_CELL * 4) // 2  # 6；marker 真中心 ≈ half 与 W-1-half
    assert abs(tl[0] - half) <= 1 and abs(tl[1] - half) <= 1
    assert abs(tr[0] - (W - 1 - half)) <= 1 and abs(tr[1] - half) <= 1
    assert abs(bl[0] - half) <= 1 and abs(bl[1] - (H - 1 - half)) <= 1
    assert abs(br[0] - (W - 1 - half)) <= 1 and abs(br[1] - (H - 1 - half)) <= 1
