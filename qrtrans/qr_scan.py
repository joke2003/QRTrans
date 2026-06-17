from __future__ import annotations
import json
from typing import List
from pyzbar.pyzbar import decode as pyzbar_decode
from PIL import Image
from .protocol import Payload, MAGIC


def scan(image: Image.Image) -> List[Payload]:
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
