from __future__ import annotations
from reedsolo import RSCodec, ReedSolomonError

BLOCK = 255  # GF(2^8) 单块总长上限


def rs_encode(data: bytes, nsym: int) -> bytes:
    if not (1 <= nsym <= BLOCK - 1):
        raise ValueError(f"nsym out of range: {nsym}")
    rsc = RSCodec(nsym)
    bd = BLOCK - nsym
    pad = (-len(data)) % bd
    data = data + b"\x00" * pad
    out = bytearray()
    for i in range(0, len(data), bd):
        out.extend(rsc.encode(data[i:i + bd]))
    return bytes(out)


def rs_decode(codeword: bytes, nsym: int, original_len: int) -> bytes:
    rsc = RSCodec(nsym)
    out = bytearray()
    for i in range(0, len(codeword), BLOCK):
        block = codeword[i:i + BLOCK]
        decoded = rsc.decode(bytearray(block))[0]
        out.extend(bytes(decoded))
    return bytes(out[:original_len])
