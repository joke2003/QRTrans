from __future__ import annotations
import qrcode
from qrcode.constants import (
    ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H,
)
from PIL import Image
from .protocol import Payload

# Version 40 = 177 模块；border=4 → 单 QR 图像边长 177+8 = 185 模块
CELL_MODULES = 185

EC_LEVELS = {
    "L": ERROR_CORRECT_L,
    "M": ERROR_CORRECT_M,
    "Q": ERROR_CORRECT_Q,
    "H": ERROR_CORRECT_H,
}

QR_VERSION = 40

# Version 40 字节模式（byte mode）数据容量上限（字节）。来源：QR Code 官方容量表。
# 显式校验的真实动机（实测 qrcode 行为）：
#   1) qrcode 在真正超容时确实会抛错，但抛的是 DataOverflowError（Exception 的直接
#      子类，非 ValueError），对调用方而言异常类型契约不稳定；
#   2) qrcode 会自动选择编码模式：纯字母数字数据走 alphanumeric（容量更大，实测
#      3000 个 'A' 不报错），因此即便数据已超过 byte 容量 2331，仍可能不抛错。
# 这里按 byte 容量提前校验，为调用方提供稳定的 ValueError 契约 + 安全余量 + 清晰错误信息。
V40_BYTE_CAPACITY = {
    "L": 2953,
    "M": 2331,
    "Q": 1663,
    "H": 1273,
}


def render(payload: Payload, module_px: int = 3, ec: str = "M") -> Image.Image:
    if ec not in EC_LEVELS:
        raise ValueError(f"unknown ec level: {ec!r}")
    data = payload.to_json()
    data_bytes = len(data.encode("utf-8"))
    # 预留 4 字节余量给模式指示符/长度位头，避免边界踩线
    capacity = V40_BYTE_CAPACITY[ec]
    if data_bytes + 4 > capacity:
        raise ValueError(
            f"payload {data_bytes}B exceeds V40/{ec} capacity {capacity}B"
        )
    qr = qrcode.QRCode(
        version=QR_VERSION,
        error_correction=EC_LEVELS[ec],
        box_size=module_px,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=False)  # 固定 V40
    img_obj = qr.make_image(fill_color="black", back_color="white")
    return img_obj.get_image()
