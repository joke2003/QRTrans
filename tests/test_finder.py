import pytest
from PIL import Image
from qrtrans.finder import draw_markers, locate_markers, interior_box, MARKER_COLOR


def test_draw_then_locate_four_corners():
    img = Image.new("RGB", (200, 150), "white")
    draw_markers(img, cell_px=4)
    corners = locate_markers(img)
    assert corners is not None and len(corners) == 4
    xs = sorted(c[0] for c in corners)
    ys = sorted(c[1] for c in corners)
    assert xs[0] < xs[-1] and ys[0] < ys[-1]   # 有左/右、上/下


def test_locate_returns_none_when_absent():
    img = Image.new("RGB", (200, 150), "white")
    assert locate_markers(img) is None


def test_interior_box_inside_corners():
    img = Image.new("RGB", (200, 150), "white")
    draw_markers(img, cell_px=4)
    corners = locate_markers(img)
    x0, y0, x1, y1 = interior_box(corners, cell_px=4, img_size=img.size)
    assert x0 > 0 and y0 > 0 and x1 < 200 and y1 < 150
    assert x1 > x0 and y1 > y0


def test_locate_survives_slight_scale():
    # 渲染后缩放 95%，仍应定位到 4 个标记
    img = Image.new("RGB", (400, 300), "white")
    draw_markers(img, cell_px=8)
    scaled = img.resize((380, 285), Image.NEAREST)
    corners = locate_markers(scaled)
    assert corners is not None and len(corners) == 4
