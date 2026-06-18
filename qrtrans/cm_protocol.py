from __future__ import annotations
import binascii
import math
import struct
from dataclasses import dataclass
from .palette import COLOR_BITS as COLOR_BITS_LOOKUP

CM_MAGIC = b"CMTX"
CM_VERSION = 1
PALETTE_VERSION = 1
_HEADER_FMT = "!4sBBBBHHHHBBI32s"


@dataclass(frozen=True)
class CmHeader:
    magic: bytes
    version: int
    palette_version: int
    k: int
    cell_px: int
    grid_w: int
    grid_h: int
    batch: str            # 8 位十六进制
    frame_index: int
    frame_total: int
    ecc_percent: int
    compressed: int
    payload_len: int
    payload_sha256: str   # 64 位十六进制


def header_to_bytes(h: CmHeader) -> bytes:
    body = struct.pack(
        _HEADER_FMT,
        CM_MAGIC, h.version, h.palette_version, h.k, h.cell_px,
        h.grid_w, h.grid_h, h.frame_index, h.frame_total, h.ecc_percent,
        h.compressed, h.payload_len, bytes.fromhex(h.payload_sha256),
    )
    batch = bytes.fromhex(h.batch)  # 4 字节
    crc = binascii.crc32(body + batch) & 0xFFFFFFFF
    return body + batch + struct.pack("!I", crc)


def header_from_bytes(b: bytes) -> CmHeader:
    body_size = struct.calcsize(_HEADER_FMT)
    body = b[:body_size]
    batch = b[body_size:body_size + 4]
    crc = struct.unpack("!I", b[body_size + 4:body_size + 8])[0]
    if (binascii.crc32(body + batch) & 0xFFFFFFFF) != crc:
        raise ValueError("header crc mismatch")
    (magic, ver, palver, k, cell_px, gw, gh, fi, ft, ecc, comp,
     plen, sha) = struct.unpack(_HEADER_FMT, body)
    if magic != CM_MAGIC:
        raise ValueError("bad magic")
    return CmHeader(
        magic=magic, version=ver, palette_version=palver, k=k, cell_px=cell_px,
        grid_w=gw, grid_h=gh, batch=batch.hex(), frame_index=fi, frame_total=ft,
        ecc_percent=ecc, compressed=comp, payload_len=plen, payload_sha256=sha.hex(),
    )


def bytes_to_indices(data: bytes, bits_per_cell: int) -> list:
    if not data:
        return []
    bits = "".join(f"{byte:08b}" for byte in data)
    pad = (-len(bits)) % bits_per_cell
    bits += "0" * pad
    return [int(bits[i:i + bits_per_cell], 2) for i in range(0, len(bits), bits_per_cell)]


def indices_to_bytes(indices: list, bits_per_cell: int, original_len: int) -> bytes:
    bits = "".join(f"{i:0{bits_per_cell}b}" for i in indices)
    out = bytearray()
    for i in range(0, len(bits), 8):
        out.append(int(bits[i:i + 8], 2))
    return bytes(out[:original_len])


# ---- 编解码共享的容量 / RS 数学 ----
HEADER_BYTES = 54 + 4 + 4   # struct body 54 + batch 4 + crc 4


def header_cells(bpc: int) -> int:
    """头序列化后占用的单元格数 = ceil(HEADER_BYTES*8 / bpc)。"""
    return math.ceil(HEADER_BYTES * 8 / bpc)


def nsym(ecc_percent: int) -> int:
    """ecc_percent → RS 冗余字节数（钳到 [2, 254]，与 rs.BLOCK 一致）。"""
    return max(2, min(254, round(255 * ecc_percent / 100)))


def codeword_len(payload_len: int, nsym_val: int) -> int:
    """给定原始数据块长度与 nsym，返回 RS 编码后的码字字节数。

    rs.rs_encode 把数据按 (255-nsym) 分块、每块扩到 255；码字 = num_blocks*255。
    空输入不 pad（pad=0，循环不执行），rs.rs_encode(b"", n) 返回 0 字节，
    故 payload_len<=0 时返回 0 与之对齐（实测确认，非 255）。
    """
    if payload_len <= 0:
        return 0
    bd = 255 - nsym_val
    num_blocks = math.ceil(payload_len / bd)
    return num_blocks * 255
