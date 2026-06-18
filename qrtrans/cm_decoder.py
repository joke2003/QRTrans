from __future__ import annotations
import hashlib
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image

from . import fs_walk
from .palette import build_palette, nearest, COLOR_BITS
from . import cm_protocol, rs
from .finder import locate_markers, interior_box, MARKER_CELL
from .progress import ProgressCallback, ProgressEvent


@dataclass
class CmDecodeResult:
    files_written: List[str] = field(default_factory=list)
    dirs_created: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)


def is_colormatrix_frame(image: Image.Image) -> bool:
    return locate_markers(image) is not None


# cell_px 探测候选：解码端不知道 cell_px，逐个尝试直到头自洽（头里写的就是 cell_px）。
_CANDIDATE_CELL_PX = (2, 3, 4, 5, 6, 8, 10)
# k 探测候选：头里也写了 k，但需先按某 k 解头才能读到它。
_CANDIDATE_K = (16, 4, 8, 32, 64)


def _sample_interior_rgbs(image, x0, y0, cell_px, iw, ih, count=None):
    """按编码端行列顺序（行优先）采样内部单元中心的 RGB。

    interior_box 已剔除 finder 标记边框，返回的 bbox 即内部区域，
    故第 (col,row) 个内部单元中心 = (x0+(col+0.5)*cell_px, y0+(row+0.5)*cell_px)。
    """
    px = image.load()
    out = []
    for r in range(ih):
        for c in range(iw):
            if count is not None and len(out) >= count:
                return out
            cx = int(x0 + (c + 0.5) * cell_px)
            cy = int(y0 + (r + 0.5) * cell_px)
            out.append(px[cx, cy][:3])
    return out


def _try_decode_header(image, corners, cell_px):
    """在该 cell_px 假设下采样头区并尝试解头。

    成功返回 (header, x0, y0, iw, ih, palette, bpc)，否则 None。
    命中条件：header_from_bytes 通过 CRC/magic 校验，且 header.cell_px==cell_px、
    header.k==k，且由 bbox 反推的内部宽高 == header.grid_{w,h}-2*MARKER_CELL。
    """
    x0, y0, x1, y1 = interior_box(corners, cell_px, image.size)
    # interior_box 已剔除标记边框：bbox 宽高 / cell_px 直接就是内部单元数。
    iw = round((x1 - x0) / cell_px)
    ih = round((y1 - y0) / cell_px)
    if iw <= 0 or ih <= 0:
        return None
    # 先采一块足够覆盖最大 bpc 头区的前若干单元，再对每个候选 k 切片试解。
    need = max(cm_protocol.header_cells(COLOR_BITS[k]) for k in _CANDIDATE_K)
    if iw * ih < need:
        return None
    rgbs = _sample_interior_rgbs(image, x0, y0, cell_px, iw, ih, count=need)
    if len(rgbs) < need:
        return None
    for k in _CANDIDATE_K:
        bpc = COLOR_BITS[k]
        hcells = cm_protocol.header_cells(bpc)
        palette = build_palette(k)
        idx = [nearest(palette, rgb) for rgb in rgbs[:hcells]]
        try:
            hb = cm_protocol.indices_to_bytes(idx, bpc, cm_protocol.HEADER_BYTES)
            header = cm_protocol.header_from_bytes(hb)
        except ValueError:
            continue
        if header.cell_px == cell_px and header.k == k:
            exp_iw = header.grid_w - 2 * MARKER_CELL
            exp_ih = header.grid_h - 2 * MARKER_CELL
            if exp_iw == iw and exp_ih == ih:
                return (header, x0, y0, iw, ih, palette, bpc)
    return None


def _decode_one_frame(image):
    """单帧→(header, chunk)。探测 cell_px/k，精确截断 payload 区，RS 解码。"""
    corners = locate_markers(image)
    if corners is None:
        return None
    for cell_px in _CANDIDATE_CELL_PX:
        info = _try_decode_header(image, corners, cell_px)
        if info is None:
            continue
        header, x0, y0, iw, ih, palette, bpc = info
        all_rgbs = _sample_interior_rgbs(image, x0, y0, cell_px, iw, ih)
        all_idx = [nearest(palette, rgb) for rgb in all_rgbs]
        hcells = cm_protocol.header_cells(bpc)
        pay_idx = all_idx[hcells:]

        # 关键（审查 I-1）：payload 区可能未被填满（留白=白）。
        # 只取 RS 码字字节数对应的单元数，转字节后喂 rs_decode，避免留白像素→垃圾字节。
        nsym_v = cm_protocol.nsym(header.ecc_percent)
        cw_len = cm_protocol.codeword_len(header.payload_len, nsym_v)
        if cw_len <= 0:
            chunk = b""
            return (header, chunk)
        pay_cells_need = -(-(cw_len * 8) // bpc)  # ceil
        if pay_cells_need > len(pay_idx):
            return None
        pay_idx = pay_idx[:pay_cells_need]
        cw_bytes = cm_protocol.indices_to_bytes(pay_idx, bpc, cw_len)
        try:
            chunk = rs.rs_decode(cw_bytes, nsym_v, header.payload_len)
        except Exception:
            return None
        return (header, chunk)
    return None


def colormatrix_decode(input_path: Path, output: Path,
                       progress: Optional[ProgressCallback] = None) -> CmDecodeResult:
    images = fs_walk.gather_images(input_path)
    total = len(images)
    frames = []
    for i, img_path in enumerate(images, start=1):
        with Image.open(img_path) as img:
            img.load()
            frame = _decode_one_frame(img)
        if frame is not None:
            frames.append(frame)
        if progress is not None:
            progress(ProgressEvent("scan", i, total))

    result = CmDecodeResult()
    if not frames:
        raise ValueError("no colormatrix frames found")

    frames.sort(key=lambda x: x[0].frame_index)
    frame_total = frames[0][0].frame_total
    present = {h.frame_index for h, _ in frames}
    expected = set(range(1, frame_total + 1))
    if present != expected:
        missing = sorted(expected - present)
        result.warnings.append(f"missing frames {missing}")
        result.failed.append("incomplete batch")
        raise ValueError(f"missing frames {missing}")

    payload = b"".join(chunk for _, chunk in frames)
    if frames[0][0].compressed == 1:
        payload = zlib.decompress(payload)
    if hashlib.sha256(payload).hexdigest() != frames[0][0].payload_sha256:
        raise ValueError("payload sha256 mismatch")

    files, dirs = _parse_payload(payload)
    _write_output(files, dirs, output)
    if progress is not None:
        progress(ProgressEvent("reassemble", len(files), len(files)))
    result.files_written = [f.relpath for f in files]
    result.dirs_created = [d.relpath for d in dirs]
    return result


def _parse_payload(payload: bytes):
    """对称 cm_encoder._build_payload：
    4B 条数 + 每条(type1 + relpath(2B len + utf8) + content_len4B) + 末尾文件 blob 顺序拼接。"""
    files: List[fs_walk.FileRecord] = []
    dirs: List[fs_walk.DirRecord] = []
    pos = 0
    (count,) = struct.unpack_from("!I", payload, pos); pos += 4
    metas = []
    for _ in range(count):
        t = payload[pos:pos + 1]; pos += 1
        (rlen,) = struct.unpack_from("!H", payload, pos); pos += 2
        relpath = payload[pos:pos + rlen].decode("utf-8"); pos += rlen
        (clen,) = struct.unpack_from("!I", payload, pos); pos += 4
        metas.append((t, relpath, clen))
    for t, relpath, clen in metas:
        content = payload[pos:pos + clen]; pos += clen
        if t == b"F":
            files.append(fs_walk.FileRecord(relpath, content))
        else:
            dirs.append(fs_walk.DirRecord(relpath))
    return files, dirs


def _write_output(files, dirs, output: Path) -> None:
    """输出形态沿用主程序语义（README）：内容自动判定。
    单文件内容→写为单文件；目录内容（含目录标记或多文件）→重建目录。"""
    if len(files) == 1 and not dirs:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(files[0].content)
    else:
        fs_walk.rebuild(files, dirs, output)
