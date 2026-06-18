from __future__ import annotations
from .finder import locate_markers
from PIL import Image


def is_colormatrix_frame(image: Image.Image) -> bool:
    return locate_markers(image) is not None
