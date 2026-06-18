from __future__ import annotations
import binascii
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
