import pytest
from PIL import Image
from qrtrans.array_pack import (
    auto_grid, parse_grid, pack, paginate, BANNER_HEIGHT, FrameSpec,
)
from qrtrans.qr_render import CELL_MODULES

def test_auto_grid_default_1920x1080_3px():
    rows, cols = auto_grid(1920, 1080, module_px=3, label=True)
    assert (rows, cols) == (1, 3)

def test_auto_grid_2px_aggressive():
    rows, cols = auto_grid(1920, 1080, module_px=2, label=True)
    assert (rows, cols) == (2, 5)   # 10 QR/帧

def test_auto_grid_label_off_allows_more_rows():
    rows_on, _ = auto_grid(1080, 1080, module_px=3, label=True)
    rows_off, _ = auto_grid(1080, 1080, module_px=3, label=False)
    assert rows_off >= rows_on

def test_parse_grid_rxc():
    assert parse_grid("3x1") == (1, 3)   # rows x cols -> (rows, cols)
    assert parse_grid("5x2") == (2, 5)

def test_parse_grid_invalid():
    with pytest.raises(ValueError):
        parse_grid("abc")
    with pytest.raises(ValueError):
        parse_grid("0x0")

def test_paginate_splits_into_frames():
    items = list(range(7))
    frames = paginate(items, per_frame=3)
    assert frames == [[0, 1, 2], [3, 4, 5], [6]]

def test_paginate_empty():
    assert paginate([], per_frame=3) == [[]]

def test_pack_frame_dimensions_and_count():
    cell_px = CELL_MODULES * 3
    imgs = [Image.new("L", (cell_px, cell_px), "black") for _ in range(3)]
    spec = FrameSpec(rows=1, cols=3, module_px=3, label=True)
    frame = pack(imgs, spec, batch="abc12345", frame_index=1, frame_total=2)
    expected_w = 3 * cell_px
    expected_h = cell_px + BANNER_HEIGHT
    assert frame.size == (expected_w, expected_h)

def test_pack_partial_frame_pads_with_white():
    cell_px = CELL_MODULES * 3
    imgs = [Image.new("L", (cell_px, cell_px), "black")]  # 只 1 张，3 列
    spec = FrameSpec(rows=1, cols=3, module_px=3, label=False)
    frame = pack(imgs, spec, batch="abc12345", frame_index=1, frame_total=1)
    assert frame.size == (3 * cell_px, cell_px)
    # 右下角应为白（RGB 模式，返回三元组）
    px = frame.getpixel((3 * cell_px - 1, cell_px - 1))
    assert px == (255, 255, 255)
