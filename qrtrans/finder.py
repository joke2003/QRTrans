from __future__ import annotations
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw

MARKER_COLOR = (0, 0, 0)
MARKER_BG = (255, 255, 255)
MARKER_CELL = 3  # 标记边长（单元格数）


def _marker_size_px(cell_px: int) -> int:
    return MARKER_CELL * cell_px


def draw_markers(canvas: Image.Image, cell_px: int) -> None:
    """在 4 角画 finder 标记：白底 + 黑块。"""
    d = ImageDraw.Draw(canvas)
    s = _marker_size_px(cell_px)
    W, H = canvas.size
    for (x0, y0) in [(0, 0), (W - s, 0), (0, H - s), (W - s, H - s)]:
        d.rectangle([x0, y0, x0 + s - 1, y0 + s - 1], fill=MARKER_COLOR)


def locate_markers(image: Image.Image) -> Optional[List[Tuple[int, int]]]:
    """找 4 角的黑块中心。简单实现：在 4 个角区域内找黑色质心。"""
    W, H = image.size
    px = image.load()
    zone_w, zone_h = W // 2, H // 2
    zones = [(0, 0), (zone_w, 0), (0, zone_h), (zone_w, zone_h)]
    centers = []
    for (zx, zy) in zones:
        # 取该象限外角侧的 1/4 子区
        x_lo = zx + (0 if zx == 0 else zone_w // 2)
        x_hi = zx + (zone_w if zx == 0 else zone_w)
        y_lo = zy + (0 if zy == 0 else zone_h // 2)
        y_hi = zy + (zone_h if zy == 0 else zone_h)
        black_pts = []
        step_x = max(1, (x_hi - x_lo) // 32)
        step_y = max(1, (y_hi - y_lo) // 32)
        for y in range(y_lo, y_hi, step_y):
            for x in range(x_lo, x_hi, step_x):
                r, g, b = px[x, y][:3]
                if r < 64 and g < 64 and b < 64:
                    black_pts.append((x, y))
        if not black_pts:
            return None
        cx = sum(p[0] for p in black_pts) // len(black_pts)
        cy = sum(p[1] for p in black_pts) // len(black_pts)
        centers.append((cx, cy))
    centers.sort(key=lambda p: (p[1], p[0]))
    top = sorted(centers[:2], key=lambda p: p[0])
    bot = sorted(centers[2:], key=lambda p: p[0])
    return top + bot   # [TL, TR, BL, BR]


def interior_box(corners, cell_px: int, img_size) -> Tuple[int, int, int, int]:
    """由 4 标记中心 + cell_px 推内部网格 bbox。"""
    tl, tr, bl, br = corners
    s = _marker_size_px(cell_px) // 2
    x0 = tl[0] + s
    y0 = tl[1] + s
    x1 = br[0] - s
    y1 = br[1] - s
    return (x0, y0, x1, y1)
