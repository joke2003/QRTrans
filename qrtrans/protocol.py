from __future__ import annotations
from dataclasses import dataclass, asdict
import json
import posixpath

MAGIC = "QRT"
PROTOCOL_VERSION = 1
SUPPORTED_VERSIONS = {1}


class ProtocolError(Exception):
    pass


@dataclass(frozen=True)
class Payload:
    magic: str
    ver: int
    batch: str
    type: str          # "file" | "dir"
    fid: str
    fn: str
    path: str          # posix 相对路径
    ci: int
    tc: int
    enc: str           # "b64"
    sha256: str
    data: str          # base64; dir 为 ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, s: str) -> "Payload":
        try:
            d = json.loads(s)
            return cls(**d)
        except (ValueError, TypeError) as e:
            raise ProtocolError(f"bad payload json: {e}") from e


def is_safe_relpath(path: str) -> bool:
    if not path or path.startswith("/"):
        return False
    norm = posixpath.normpath(path)
    if norm == ".." or norm.startswith("../") or norm == ".":
        if norm == ".":
            return True
        return False
    if "/.." in norm or norm == "..":
        return False
    return True


def validate(payload: Payload) -> None:
    if payload.magic != MAGIC:
        raise ProtocolError(f"bad magic: {payload.magic!r}")
    if payload.ver not in SUPPORTED_VERSIONS:
        raise ProtocolError(f"unsupported version: {payload.ver}")
    if payload.type not in ("file", "dir"):
        raise ProtocolError(f"bad type: {payload.type!r}")
    if payload.enc != "b64":
        raise ProtocolError(f"bad enc: {payload.enc!r}")
    if not is_safe_relpath(payload.path):
        raise ProtocolError(f"unsafe path: {payload.path!r}")
    if payload.type == "dir":
        if not payload.path.endswith("/"):
            raise ProtocolError("dir path must end with '/'")
        if payload.data != "" or payload.sha256 != "":
            raise ProtocolError("dir payload must have empty data/sha256")
    else:
        if payload.tc < 1 or not (0 <= payload.ci < payload.tc):
            raise ProtocolError(f"bad ci/tc: {payload.ci}/{payload.tc}")
        if payload.sha256 == "":
            raise ProtocolError("file payload must have non-empty sha256")
        if payload.path.endswith("/"):
            raise ProtocolError("file path must not end with '/'")


def make_file_payload(*, batch, fid, relpath, fn, ci, tc, sha256, data_b64) -> Payload:
    return Payload(
        magic=MAGIC, ver=PROTOCOL_VERSION, batch=batch,
        type="file", fid=fid, fn=fn, path=relpath,
        ci=ci, tc=tc, enc="b64", sha256=sha256, data=data_b64,
    )


def make_dir_payload(*, batch, fid, relpath, fn) -> Payload:
    if not relpath.endswith("/"):
        relpath = relpath + "/"
    return Payload(
        magic=MAGIC, ver=PROTOCOL_VERSION, batch=batch,
        type="dir", fid=fid, fn=fn, path=relpath,
        ci=0, tc=1, enc="b64", sha256="", data="",
    )
