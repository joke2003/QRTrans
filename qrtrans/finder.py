from __future__ import annotations
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw

# 标记用「保留的离网格颜色」：调色板只取 {0,64,128,191,255}^3 内的色，
# 这里每个分量都落在网格值之间的中点附近（32/223/96），与任何调色板色都相距足够远，
# 故内部单元格内容（即便也是深色）永远不会和标记混淆。
MARKER_COLOR = (32, 223, 96)
MARKER_TOL = 24
MARKER_CELL = 3  # 标记边长（单元格数）
# 最大 marker 边长（像素）= MARKER_CELL × 最大合法 cell_px(12)；用于精修窗口半径。
_MAX_MARKER_PX = MARKER_CELL * 12


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


def _refine_marker_center(px, approx_x: int, approx_y: int, W: int, H: int):
    """在粗质心附近全分辨率扫描，取 marker 像素外接矩形中心。

    粗采样质心会随采样步长(step=min(W,H)//200)与 marker 对齐情况偏移：
    如 2560 宽图 step=7、marker 12px，采样到 {0,7} → 质心 3（真中心 5.5），
    使 interior_box 起点偏移 ~3px，采样错过单元中心、header 字节错乱。
    marker 是实心方块，外接矩形中心 = 真中心，与步长/分辨率无关。
    """
    half = _MAX_MARKER_PX
    x_lo, x_hi = max(0, approx_x - half), min(W - 1, approx_x + half)
    y_lo, y_hi = max(0, approx_y - half), min(H - 1, approx_y + half)
    xmin = ymin = None
    xmax = ymax = None
    for y in range(y_lo, y_hi + 1):
        for x in range(x_lo, x_hi + 1):
            if _is_marker_rgb(px[x, y]):
                if xmin is None or x < xmin:
                    xmin = x
                if xmax is None or x > xmax:
                    xmax = x
                if ymin is None or y < ymin:
                    ymin = y
                if ymax is None or y > ymax:
                    ymax = y
    if xmin is None:
        return (approx_x, approx_y)
    return ((xmin + xmax) // 2, (ymin + ymax) // 2)


def locate_markers(image: Image.Image) -> Optional[List[Tuple[int, int]]]:
    """全图稀疏扫描找 MARKER_COLOR 像素，按 4 象限分组取质心，再局部精修。

    返回 [TL, TR, BL, BR]（marker 中心）；任一象限无标记则返回 None。"""
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
        centers.append(_refine_marker_center(px, cx, cy, W, H))
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
