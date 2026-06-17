from __future__ import annotations
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from PIL import Image

from . import chunker, fs_walk, qr_scan
from .chunker import Chunk
from .fs_walk import FileRecord, DirRecord
from .protocol import Payload, ProtocolError, validate


class DecodeError(Exception):
    pass


@dataclass(frozen=True)
class DecodeOptions:
    strict: bool = False


@dataclass
class DecodeResult:
    files_written: List[str] = field(default_factory=list)
    dirs_created: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)


def _gather_payloads(input_path: Path) -> List[Payload]:
    images = fs_walk.gather_images(input_path)
    payloads: List[Payload] = []
    for img_path in images:
        with Image.open(img_path) as img:
            img.load()
            payloads.extend(qr_scan.scan(img))
    return payloads


def _filter_and_group(payloads):
    """返回 (file_groups, dir_payloads, warnings)。
    file_groups: dict[fid] -> list[Payload]（仅 type=file 且校验通过）"""
    file_groups = defaultdict(list)
    dirs = []
    warnings = []
    seen_batch = {}
    batches = set()
    for pl in payloads:
        try:
            validate(pl)
        except ProtocolError as e:
            warnings.append(f"invalid payload skipped: {e}")
            continue
        if seen_batch.get(pl.fid, pl.batch) != pl.batch:
            warnings.append(f"fid {pl.fid} 出现多个 batch，跳过后续")
            continue
        seen_batch[pl.fid] = pl.batch
        batches.add(pl.batch)
        if pl.type == "dir":
            dirs.append(pl)
        else:
            file_groups[pl.fid].append(pl)
    if len(batches) > 1:
        warnings.append(f"multiple batches detected in input: {sorted(batches)}")
    return file_groups, dirs, warnings


def _reassemble_file(file_payloads: List[Payload]) -> "_FileReas":
    """重组单个文件的所有分块。返回 _FileReas（ok/reason/data/sha256）。

    良性重复（同 ci 同 data，如目录含重复图像）按 ci 去重保留首个；
    真 conflict（同 ci 异 data）由下方 sha256 校验兜底。
    """
    relpath = file_payloads[0].path
    fn = file_payloads[0].fn
    by_ci = {}
    for p in file_payloads:
        if p.ci not in by_ci:
            by_ci[p.ci] = p
    chunks = [Chunk(p.ci, p.tc, p.sha256, p.data) for p in by_ci.values()]
    tc = chunks[0].tc
    complete, data, sha = chunker.reassemble(chunks)
    if not complete:
        missing = sorted(set(range(tc)) - set(by_ci.keys()))
        return _FileReas(relpath, fn, None, sha, False,
                         f"missing chunks {missing} for {relpath}")
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha:
        return _FileReas(relpath, fn, None, sha, False,
                         f"sha256 mismatch for {relpath}")
    return _FileReas(relpath, fn, data, sha, True, "")


@dataclass
class _FileReas:
    relpath: str
    fn: str
    data: Optional[bytes]
    sha256: str
    ok: bool
    reason: str


def decode(input_path: Path, output: Path, options: DecodeOptions) -> DecodeResult:
    result = DecodeResult()
    payloads = _gather_payloads(input_path)
    if not payloads:
        raise DecodeError(f"no QRT payloads found in {input_path}")

    file_groups, dir_payloads, warnings = _filter_and_group(payloads)
    result.warnings.extend(warnings)

    reassembled: List[_FileReas] = []
    for fid, group in file_groups.items():
        reassembled.append(_reassemble_file(group))

    # 决定输出形态：无目录标记、且仅 1 个 ok 文件组 -> 写单文件
    n_ok_files = sum(1 for r in reassembled if r.ok)
    n_dir = len(dir_payloads)
    single_file_mode = n_ok_files == 1 and n_dir == 0 and len(reassembled) == 1

    # strict 校验
    failed = [r for r in reassembled if not r.ok]
    if failed and options.strict:
        for r in failed:
            result.warnings.append(r.reason)
        result.failed = [r.relpath for r in failed]
        raise DecodeError("strict mode: " + "; ".join(r.reason for r in failed))

    # 失败项告警
    for r in failed:
        result.warnings.append(r.reason)
        result.failed.append(r.relpath)

    if single_file_mode:
        r = reassembled[0]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(r.data)
        result.files_written.append(str(output))
        return result

    # 目录模式
    files = [FileRecord(r.relpath, r.data) for r in reassembled if r.ok]
    dirs = [DirRecord(p.path) for p in dir_payloads]
    if files or dirs:
        fs_walk.rebuild(files, dirs, output)
        result.files_written = [f.relpath for f in files]
        result.dirs_created = [d.relpath for d in dirs]
    return result
