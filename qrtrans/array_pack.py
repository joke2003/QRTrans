from __future__ import annotations
from dataclasses import dataclass
from typing import List, TypeVar
from PIL import Image, ImageDraw
from .qr_render import CELL_MODULES

BANNER_HEIGHT = 40
T = TypeVar("T")


@dataclass(frozen=True)
class FrameSpec:
    rows: int
    cols: int
    module_px: int
    label: bool

    @property
    def cell_px(self) -> int:
        return CELL_MODULES * self.module_px

    @property
    def per_frame(self) -> int:
        return self.rows * self.cols


def auto_grid(screen_w: int, screen_h: int, module_px: int, label: bool):
    cell_px = CELL_MODULES * module_px
    cols = max(1, screen_w // cell_px)
    avail_h = screen_h - (BANNER_HEIGHT if label else 0)
    rows = max(1, avail_h // cell_px)
    return rows, cols


def parse_grid(s: str):
    """'COLSxROWS' -> (rows, cols)。"""
    if "x" not in s.lower():
        raise ValueError(f"bad grid: {s!r}")
    parts = s.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"bad grid: {s!r}")
    try:
        c, r = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"bad grid: {s!r}")
    if r < 1 or c < 1:
        raise ValueError(f"grid must be >=1: {s!r}")
    return r, c


def paginate(items: List[T], per_frame: int) -> List[List[T]]:
    if per_frame < 1:
        raise ValueError("per_frame must be >=1")
    return [items[i:i + per_frame] for i in range(0, len(items), per_frame)] or [[]]


def pack(
    images: List[Image.Image],
    spec: FrameSpec,
    batch: str,
    frame_index: int,
    frame_total: int,
) -> Image.Image:
    cell_px = spec.cell_px
    width = spec.cols * cell_px
    height = spec.rows * cell_px + (BANNER_HEIGHT if spec.label else 0)
    mode = "RGB"
    canvas = Image.new(mode, (width, height), "white")

    banner_h = BANNER_HEIGHT if spec.label else 0
    for i, img in enumerate(images):
        if i >= spec.per_frame:
            break
        r = i // spec.cols
        c = i % spec.cols
        x = c * cell_px
        y = banner_h + r * cell_px
        paste_img = img.convert(mode)
        if paste_img.size != (cell_px, cell_px):
            paste_img = paste_img.resize((cell_px, cell_px), Image.Resampling.NEAREST)
        canvas.paste(paste_img, (x, y))

    if spec.label:
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, 0, width, BANNER_HEIGHT - 1], fill="black")
        text = f"batch={batch} frame {frame_index}/{frame_total}"
        draw.text((10, 10), text, fill="white")

    return canvas
