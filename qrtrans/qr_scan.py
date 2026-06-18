from __future__ import annotations
import json
from typing import List
from PIL import Image
from .protocol import Payload, MAGIC


def scan(image: Image.Image) -> List[Payload]:
    # 延迟导入：pyzbar 在 import 时会立即加载 libzbar 共享库。
    # 延迟到真正需要解码时再导入，使包导入（与 encode/--help 路径）不依赖 libzbar。
    from pyzbar.pyzbar import decode as pyzbar_decode
    results = pyzbar_decode(image)
    payloads: List[Payload] = []
    for r in results:
        if r.type != "QRCODE":
            continue
        try:
            text = r.data.decode("utf-8")
            d = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(d, dict) or d.get("magic") != MAGIC:
            continue
        try:
            payloads.append(Payload(**d))
        except TypeError:
            continue
    return payloads
