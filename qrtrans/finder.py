from __future__ import annotations
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw

# 标记用「保留的离网格颜色」：调色板只取 {0,64,128,191,255}^3 内的色，
# 这里每个分量都落在网格值之间的中点附近（32/223/96），与任何调色板色都相距足够远，
# 故内部单元格内容（即便也是深色）永远不会和标记混淆。
MARKER_COLOR = (32, 223, 96)
MARKER_TOL = 24
MARKER_CELL = 3  # 标记边长（单元格数）


def _marker_size_px(cell_px: int) -> int:
    return MARKER_CELL * cell_px


def _is_marker_rgb(rgb) -> bool:
    r, g, b = rgb[0], rgb[1], rgb[2]
    return (abs(r - MARKER_COLOR[0]) <= MARKER_TOL
            and abs(g - MARKER_COLOR[1]) <= MARKER_TOL
            and abs(b - MARKER_COLOR[2]) <= MARKER_TOL)


def draw_markers(canvas: Image.Image, cell_px: int) -> None:
    """在 4 角画 finder 标记（MARKER_COLOR 实心块）。"""
    d = ImageDraw.Draw(canvas)
    s = _marker_size_px(cell_px)
    W, H = canvas.size
    for (x0, y0) in [(0, 0), (W - s, 0), (0, H - s), (W - s, H - s)]:
        d.rectangle([x0, y0, x0 + s - 1, y0 + s - 1], fill=MARKER_COLOR)


def locate_markers(image: Image.Image) -> Optional[List[Tuple[int, int]]]:
    """全图稀疏扫描找 MARKER_COLOR 像素，按 4 象限分组取质心。
    返回 [TL, TR, BL, BR]；任一象限无标记则返回 None。"""
    W, H = image.size
    px = image.load()
    quads = {"TL": [], "TR": [], "BL": [], "BR": []}
    step = max(1, min(W, H) // 200)
    for y in range(0, H, step):
        row_q = "T" if y < H // 2 else "B"
        for x in range(0, W, step):
            if _is_marker_rgb(px[x, y]):
                col_q = "L" if x < W // 2 else "R"
                quads[row_q + col_q].append((x, y))
    centers = []
    for q in ("TL", "TR", "BL", "BR"):
        pts = quads[q]
        if not pts:
            return None
        cx = sum(p[0] for p in pts) // len(pts)
        cy = sum(p[1] for p in pts) // len(pts)
        centers.append((cx, cy))
    return centers   # [TL, TR, BL, BR]


def interior_box(corners, cell_px: int, img_size=None) -> Tuple[int, int, int, int]:
    """由 4 标记中心 + 半标记宽推内部网格 bbox（用 4 角，抗轻微非对称）。"""
    tl, tr, bl, br = corners
    half = _marker_size_px(cell_px) // 2
    x0 = min(tl[0], bl[0]) + half
    y0 = min(tl[1], tr[1]) + half
    x1 = max(tr[0], br[0]) - half
    y1 = max(bl[1], br[1]) - half
    return (x0, y0, x1, y1)
