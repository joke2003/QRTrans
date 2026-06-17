from __future__ import annotations
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image

from . import chunker, fs_walk, protocol, qr_render
from .array_pack import (
    auto_grid, parse_grid, paginate, pack, FrameSpec,
)
from .fs_walk import FileRecord, DirRecord


@dataclass(frozen=True)
class EncodeOptions:
    mode: str                       # "single" | "array"
    screen: Tuple[int, int]
    module_px: int
    grid: str                       # "WxH" 形如 "3x1"，或 "auto"
    ec: str
    chunk_raw_bytes: int
    label: bool
    batch: str                      # "" -> 自动生成


@dataclass
class EncodeResult:
    batch: str
    payload_count: int
    output_files: List[Path] = field(default_factory=list)


def _new_batch_id() -> str:
    return secrets.token_hex(4)   # 8 位十六进制


def _build_payloads(
    files: List[FileRecord], dirs: List[DirRecord], batch: str, chunk_raw_bytes: int
) -> List[protocol.Payload]:
    payloads: List[protocol.Payload] = []
    for idx, f in enumerate(files):
        fid = f"f{idx:02d}"
        chunks = chunker.split(f.content, chunk_raw_bytes)
        for ch in chunks:
            payloads.append(protocol.make_file_payload(
                batch=batch, fid=fid, relpath=f.relpath, fn=Path(f.relpath).name,
                ci=ch.ci, tc=ch.tc, sha256=ch.sha256, data_b64=ch.data_b64,
            ))
    for idx, d in enumerate(dirs):
        did = f"d{idx:02d}"
        payloads.append(protocol.make_dir_payload(
            batch=batch, fid=did, relpath=d.relpath, fn="",
        ))
    return payloads


def _resolve_framespec(options: EncodeOptions) -> FrameSpec:
    sw, sh = options.screen
    if options.grid == "auto":
        rows, cols = auto_grid(sw, sh, options.module_px, options.label)
    else:
        rows, cols = parse_grid(options.grid)
    return FrameSpec(rows=rows, cols=cols, module_px=options.module_px, label=options.label)


def encode(input_path: Path, out_dir: Path, options: EncodeOptions) -> EncodeResult:
    if options.mode not in ("single", "array"):
        raise ValueError(f"bad mode: {options.mode!r}")

    files, dirs = fs_walk.collect(input_path)
    if not files and not dirs:
        raise fs_walk.FsError(f"nothing to encode under {input_path}")

    batch = options.batch or _new_batch_id()
    payloads = _build_payloads(files, dirs, batch, options.chunk_raw_bytes)

    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: List[Path] = []

    if options.mode == "single":
        for i, pl in enumerate(payloads, start=1):
            img = qr_render.render(pl, module_px=options.module_px, ec=options.ec)
            fname = f"qrtrans_{batch}_{i:04d}.png"
            p = out_dir / fname
            img.save(p, "PNG")
            outputs.append(p)
    else:
        spec = _resolve_framespec(options)
        images = [qr_render.render(pl, module_px=options.module_px, ec=options.ec)
                  for pl in payloads]
        frames = paginate(images, spec.per_frame) if images else []
        total = len(frames)
        for idx, frame_imgs in enumerate(frames, start=1):
            canvas = pack(frame_imgs, spec, batch=batch,
                          frame_index=idx, frame_total=total)
            fname = f"qrtrans_{batch}_frame_{idx:02d}.png"
            p = out_dir / fname
            canvas.save(p, "PNG")
            outputs.append(p)

    return EncodeResult(batch=batch, payload_count=len(payloads), output_files=outputs)
