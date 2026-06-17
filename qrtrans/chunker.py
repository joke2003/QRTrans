from __future__ import annotations
import base64
import hashlib
from dataclasses import dataclass
from typing import List, Tuple

DEFAULT_CHUNK_RAW_BYTES = 1300


@dataclass(frozen=True)
class Chunk:
    ci: int
    tc: int
    sha256: str
    data_b64: str


def split(content: bytes, chunk_raw_bytes: int = DEFAULT_CHUNK_RAW_BYTES) -> List[Chunk]:
    sha = hashlib.sha256(content).hexdigest()
    if len(content) == 0:
        return [Chunk(0, 1, sha, base64.b64encode(b"").decode("ascii"))]
    tc = (len(content) + chunk_raw_bytes - 1) // chunk_raw_bytes
    out: List[Chunk] = []
    for ci in range(tc):
        piece = content[ci * chunk_raw_bytes:(ci + 1) * chunk_raw_bytes]
        out.append(Chunk(ci, tc, sha, base64.b64encode(piece).decode("ascii")))
    return out


def reassemble(chunks: List[Chunk]) -> Tuple[bool, bytes, str]:
    if not chunks:
        return False, b"", ""
    tc = chunks[0].tc
    sha = chunks[0].sha256
    by_ci = {c.ci: c for c in chunks}
    if len(by_ci) != tc or set(by_ci.keys()) != set(range(tc)):
        return False, b"", sha
    data = b"".join(base64.b64decode(by_ci[i].data_b64) for i in range(tc))
    return True, data, sha
