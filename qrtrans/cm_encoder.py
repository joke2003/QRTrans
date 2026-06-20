from __future__ import annotations
import hashlib
import secrets
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw

from . import fs_walk
from .palette import build_palette, COLOR_BITS
from . import cm_protocol, rs
from .cm_protocol import nsym as _nsym
from .finder import draw_markers, MARKER_CELL
from .progress import ProgressCallback, ProgressEvent

LABEL_HEIGHT = 40   # label 横幅高度（像素），位于 grid 正下方


def _payload_bytes_per_frame(payload_cells: int, bpc: int, nsym_val: int) -> int:
    """每帧 RS 编码前的原始数据字节数。

    _render_frame 渲染的是 RS 编码后的码字（每块 255B），因此可用单元换算成
    码字字节后再倒推 RS 块数与原始数据字节，确保码字 bit-pack 后不溢出
    payload_cells，从而 head_idx + pay_idx <= 内部网格单元数，杜绝静默截断。
    """
    max_codeword_bytes = (payload_cells * bpc) // 8
    num_blocks = max_codeword_bytes // rs.BLOCK
    if num_blocks < 1:
        raise ValueError(f"screen/cell_px too small for RS codeword region")
    return num_blocks * (rs.BLOCK - nsym_val)


@dataclass(frozen=True)
class CmEncodeOptions:
    colors: int = 16
    cell_px: int = 4
    ecc_percent: int = 12
    compress: bool = True
    screen: Tuple[int, int] = (1920, 1080)
    batch: str = ""
    label: bool = True
    margin: int = 24   # 四边黑色留白（像素）；让帧==屏幕且给截图标注留边


@dataclass
class CmEncodeResult:
    batch: str
    frame_count: int
    output_files: List[Path]


def _new_batch() -> str:
    return secrets.token_hex(4)


def _normalize_batch(batch: str) -> str:
    """CmHeader 要求 batch 为 8 位十六进制；非 hex 输入则确定性派生一个。"""
    if batch:
        try:
            b = bytes.fromhex(batch)
            if len(b) == 4:
                return batch.lower()
        except ValueError:
            pass
        return hashlib.sha256(batch.encode("utf-8")).hexdigest()[:8]
    return _new_batch()


def _grid_dims(screen, cell_px, margin, label):
    """grid 单元数：在屏幕内扣四边留白和 label 高度后的可用区按 cell_px 整除。

    这样 grid + 留白 + label 总尺寸 <= screen，帧画布取 screen 大小、
    其余填黑，杜绝 viewer 全屏时的裁切。
    """
    sw, sh = screen
    avail_w = sw - 2 * margin
    avail_h = sh - 2 * margin - (LABEL_HEIGHT if label else 0)
    return avail_w // cell_px, avail_h // cell_px


def colormatrix_encode(input_path: Path, out_dir: Path,
                       options: CmEncodeOptions,
                       progress: Optional[ProgressCallback] = None) -> CmEncodeResult:
    files, dirs = fs_walk.collect(input_path)
    if not files and not dirs:
        raise fs_walk.FsError(f"nothing to encode under {input_path}")

    if options.cell_px not in cm_protocol.VALID_CELL_PX:
        raise ValueError(
            f"unsupported cell_px {options.cell_px}; allowed: {cm_protocol.VALID_CELL_PX}")

    batch = _normalize_batch(options.batch)
    palette = build_palette(options.colors)
    bpc = COLOR_BITS[options.colors]
    cell_px = options.cell_px

    payload = _build_payload(files, dirs)
    sha = hashlib.sha256(payload).hexdigest()
    if options.compress:
        comp = zlib.compress(payload, 9)
        if len(comp) < len(payload):
            payload, compressed = comp, 1
        else:
            compressed = 0
    else:
        compressed = 0

    gw, gh = _grid_dims(options.screen, cell_px, options.margin, options.label)
    iw = gw - 2 * MARKER_CELL
    ih = gh - 2 * MARKER_CELL
    header_cells = cm_protocol.header_cells(bpc)
    payload_cells_per_frame = iw * ih - header_cells
    if payload_cells_per_frame < 1:
        raise ValueError(f"screen/cell_px too small for payload region")
    payload_bytes_per_frame = _payload_bytes_per_frame(
        payload_cells_per_frame, bpc, _nsym(options.ecc_percent))

    out_dir.mkdir(parents=True, exist_ok=True)
    frames_data = _chunk_with_rs(payload, payload_bytes_per_frame, _nsym(options.ecc_percent))
    frame_total = len(frames_data)
    outputs: List[Path] = []

    if progress is not None:
        progress(ProgressEvent("prepare", frame_total, frame_total))

    for idx, (frame_payload, frame_orig_len) in enumerate(frames_data, start=1):
        header = cm_protocol.CmHeader(
            magic=cm_protocol.CM_MAGIC, version=cm_protocol.CM_VERSION,
            palette_version=cm_protocol.PALETTE_VERSION, k=options.colors,
            cell_px=cell_px, grid_w=gw, grid_h=gh, batch=batch,
            frame_index=idx, frame_total=frame_total, ecc_percent=options.ecc_percent,
            compressed=compressed, payload_len=frame_orig_len, payload_sha256=sha,
        )
        img = _render_frame(header, frame_payload, palette, bpc, cell_px, gw, gh,
                            options.label, batch, idx, frame_total,
                            options.screen, options.margin)
        p = out_dir / f"qrtrans_{batch}_cm_{idx:03d}.png"
        img.save(p, "PNG")
        outputs.append(p)
        if progress is not None:
            progress(ProgressEvent("frame", idx, frame_total))

    return CmEncodeResult(batch=batch, frame_count=frame_total, output_files=outputs)


def _build_payload(files, dirs) -> bytes:
    """自描述容器：4B 条数 + 每条(type1 + relpath(2B len + utf8) + len4B) + 文件 blob 拼接。"""
    out = bytearray()
    entries = []
    blob = bytearray()
    for f in files:
        entries.append((b"F", f.relpath, len(f.content)))
        blob.extend(f.content)
    for d in dirs:
        entries.append((b"D", d.relpath, 0))
    out += struct.pack("!I", len(entries))
    for t, relpath, ln in entries:
        rp = relpath.encode("utf-8")
        out += t + struct.pack("!H", len(rp)) + rp + struct.pack("!I", ln)
    out += bytes(blob)
    return bytes(out)


def _chunk_with_rs(payload: bytes, bytes_per_frame: int, nsym: int):
    out = []
    for i in range(0, len(payload), bytes_per_frame):
        chunk = payload[i:i + bytes_per_frame]
        out.append((rs.rs_encode(chunk, nsym), len(chunk)))
    if not out:
        out.append((rs.rs_encode(b"", nsym), 0))
    return out


def _render_frame(header, frame_payload, palette, bpc, cell_px, gw, gh,
                  label, batch, idx, total, screen, margin) -> Image.Image:
    sw, sh = screen
    grid_w_px = gw * cell_px
    grid_h_px = gh * cell_px

    # 先在「网格区」大小的临时图上绘制内部单元格 + finder 标记，
    # 再 paste 到屏幕画布的 (margin, margin) 处。画布整屏黑底，杜绝 viewer 裁切。
    grid_img = Image.new("RGB", (grid_w_px, grid_h_px), "white")

    header_bytes = cm_protocol.header_to_bytes(header)
    head_idx = cm_protocol.bytes_to_indices(header_bytes, bpc)
    pay_idx = cm_protocol.bytes_to_indices(frame_payload, bpc)
    cells = head_idx + pay_idx

    iw = gw - 2 * MARKER_CELL
    ih = gh - 2 * MARKER_CELL
    d = ImageDraw.Draw(grid_img)
    ci = 0
    for r in range(MARKER_CELL, MARKER_CELL + ih):
        for c in range(MARKER_CELL, MARKER_CELL + iw):
            if ci < len(cells):
                color = palette[cells[ci]]
                x0, y0 = c * cell_px, r * cell_px
                d.rectangle([x0, y0, x0 + cell_px - 1, y0 + cell_px - 1], fill=color)
            ci += 1

    # 标记画在网格区 4 角，用 finder.draw_markers 的离网格色 MARKER_COLOR
    draw_markers(grid_img, cell_px)

    canvas = Image.new("RGB", (sw, sh), "black")
    canvas.paste(grid_img, (margin, margin))

    if label:
        dl = ImageDraw.Draw(canvas)
        ly = margin + grid_h_px
        dl.text((margin + 10, ly + 10), f"batch={batch} cm {idx}/{total}", fill="white")
    return canvas
