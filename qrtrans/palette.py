from __future__ import annotations
from typing import List, Tuple

VALID_K = (4, 8, 16, 32, 64)
COLOR_BITS = {4: 2, 8: 3, 16: 4, 32: 5, 64: 6}

# 贪心最远点的候选集（5×5×5 立方体网格，覆盖 sRGB）
_CAND = [(r, g, b)
         for r in (0, 64, 128, 191, 255)
         for g in (0, 64, 128, 191, 255)
         for b in (0, 64, 128, 191, 255)]


def build_palette(k: int) -> List[Tuple[int, int, int]]:
    """返回 K 色调色板。确定性、版本固定（属格式的一部分，勿改算法）。
    仅支持 k∈{4,8,16,32,64}。"""
    if k not in VALID_K:
        raise ValueError(f"unsupported palette size {k}; allowed: {VALID_K}")
    pts = [(128, 128, 128)]
    while len(pts) < k:
        best, best_d = None, -1
        for c in _CAND:
            if c in pts:
                continue
            d = min((c[0]-p[0])**2 + (c[1]-p[1])**2 + (c[2]-p[2])**2 for p in pts)
            if d > best_d:
                best_d, best = d, c
        pts.append(best)
    return pts


def nearest(palette, rgb) -> int:
    bi, bd = 0, 1 << 30
    for i, c in enumerate(palette):
        d = (c[0]-rgb[0])**2 + (c[1]-rgb[1])**2 + (c[2]-rgb[2])**2
        if d < bd:
            bd, bi = d, i
    return bi
