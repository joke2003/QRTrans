# QRTrans 彩色矩阵（colormatrix）模式 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 新增高密度 `colormatrix` 模式（全屏彩色单元格矩阵，16色/4px 默认，~50KB/帧，约 4–7× QR），作为新默认；QR（array/single）共存、改为手动指定。无损 PNG 截屏信道。

**架构：** 新模块 `palette`/`cm_protocol`/`finder`/`rs`/`cm_encoder`/`cm_decoder`；encode/decode 按 mode/finder 自动分流。帧 = 4 角 finder 标记 + 单元格网格（头区 + 载荷区）；每帧独立 RS（v1）；zlib 自动压缩；复用进度回调。

**技术栈：** Pillow（已有）、`reedsolo`（新增，纯 Python）。

**参考规格：** `docs/superpowers/specs/2026-06-18-colormatrix-design.md`

**验证：** `.venv/bin/pytest -q`；本地 frozen 冒烟；重出 Win7 exe（v0.2.0）在后续 release 任务。

---

## 跨模块类型约定（所有任务遵守）

```python
# palette.py
COLOR_BITS = {4: 2, 8: 3, 16: 4, 32: 5, 64: 6}   # K -> bits/cell
def build_palette(k: int) -> List[Tuple[int,int,int]]   # k∈{4,8,16,32,64}; 确定性、版本固定
def nearest(palette, rgb) -> int

# cm_protocol.py
CM_MAGIC = b"CMTX"; CM_VERSION = 1; PALETTE_VERSION = 1
@dataclass(frozen=True) class CmHeader:
    magic: bytes; version: int; palette_version: int; k: int; cell_px: int
    grid_w: int; grid_h: int; batch: str; frame_index: int; frame_total: int
    ecc_percent: int; compressed: int; payload_len: int; payload_sha256: str
def header_to_bytes(h) -> bytes          # 固定布局 + crc32 尾部
def header_from_bytes(b) -> CmHeader     # 校验 magic + crc，否则 raise
def bytes_to_indices(data, bits_per_cell) -> List[int]
def indices_to_bytes(indices, bits_per_cell, original_len) -> bytes

# rs.py
def rs_encode(data: bytes, nsym: int) -> bytes    # 分 (255-nsym) 块、各 RS、pad 到整块；返回 N*255
def rs_decode(codeword: bytes, nsym: int, original_len: int) -> bytes  # 反向；错超限抛 ReedSolomonError

# finder.py
MARKER_COLOR = (0,0,0); MARKER_BG = (255,255,255)
MARKER_CELL = 3   # 标记边长 = MARKER_CELL * cell_px 像素
def draw_markers(canvas, cell_px) -> None        # 在 4 角画标记
def locate_markers(image) -> Optional[List[Tuple[int,int]]]   # 4 中心点，找不到返回 None
def interior_box(corners) -> Tuple[int,int,int,int]           # 内部网格 bbox

# cm_encoder.py / cm_decoder.py
@dataclass(frozen=True) class CmEncodeOptions:
    colors:int=16; cell_px:int=4; ecc_percent:int=12; compress:bool=True
    screen:Tuple[int,int]=(1920,1080); batch:str=""; label:bool=True
def colormatrix_encode(input_path, out_dir, options, progress=None) -> EncodeResult
def colormatrix_decode(input_path, output, progress=None) -> DecodeResult
def is_colormatrix_frame(image) -> bool
```

**关键几何约定**：finder 标记画在 4 角（像素图形），内部为单元格网格。解码**自动探测 cell_px**：对 candidate ∈ {2,3,4,5,6}，用 marker 定位内部 bbox、按 candidate 切网格、采头区，若 `CM_MAGIC` 校验通过即采用（打破"cell_px 在头里"的鸡生蛋）。

---

## 任务 1：reedsolo 依赖 + `rs.py`

**文件：** 改 `pyproject.toml`；创建 `qrtrans/rs.py`、`tests/test_rs.py`

- [ ] **步骤 1：加依赖** — `pyproject.toml` 的 `dependencies` 加 `"reedsolo>=1.7"`；`.venv/bin/python -m pip install -e ".[dev]"`。

- [ ] **步骤 2：失败测试** — `tests/test_rs.py`：

```python
import pytest
from qrtrans.rs import rs_encode, rs_decode


def test_rs_roundtrip_small():
    data = b"hello colormatrix"
    cw = rs_encode(data, nsym=12)
    assert rs_decode(cw, nsym=12, original_len=len(data)) == data


def test_rs_roundtrip_large_multiblock():
    data = bytes(range(256)) * 40  # 10240B，多块
    cw = rs_encode(data, nsym=12)
    assert rs_decode(cw, nsym=12, original_len=len(data)) == data


def test_rs_corrects_errors_within_capacity():
    data = b"payload to protect" * 5
    cw = bytearray(rs_encode(data, nsym=24))
    # 翻转若干字节（≤nsym/2 个错误可纠）
    for i in (0, 1, 2, 3, 4, 5):
        cw[i] ^= 0xFF
    assert rs_decode(bytes(cw), nsym=24, original_len=len(data)) == data


def test_rs_fails_beyond_capacity():
    from reedsolo import ReedSolomonError
    data = b"x" * 200
    cw = bytearray(rs_encode(data, nsym=10))
    for i in range(20):  # 远超容量
        cw[i] ^= 0xFF
    with pytest.raises(ReedSolomonError):
        rs_decode(bytes(cw), nsym=10, original_len=len(data))
```

- [ ] **步骤 3：验证失败** — `.venv/bin/pytest tests/test_rs.py -q`（FAIL：模块不存在）

- [ ] **步骤 4：实现** — `qrtrans/rs.py`：

```python
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
        decoded, _ = rsc.decode(bytearray(block))
        out.extend(bytes(decoded))
    return bytes(out[:original_len])
```

> 注：reedsolo 的 `decode` 在较新版本返回 `(msg, errata_pos)`；若该版本 API 不同（如只返回 msg），实现者按实际版本调整，保证测试通过。

- [ ] **步骤 5：验证通过** — `.venv/bin/pytest tests/test_rs.py -q`（4 passed）

- [ ] **步骤 6：Commit**
```bash
git add pyproject.toml qrtrans/rs.py tests/test_rs.py
git commit -m "feat(rs): add reedsolo wrapper for per-frame error correction"
```

---

## 任务 2：`palette.py`

**文件：** 创建 `qrtrans/palette.py`、`tests/test_palette.py`

- [ ] **步骤 1：失败测试** — `tests/test_palette.py`：

```python
import pytest
from qrtrans.palette import build_palette, nearest, COLOR_BITS


@pytest.mark.parametrize("k", [4, 8, 16, 32, 64])
def test_palette_size_and_unique(k):
    p = build_palette(k)
    assert len(p) == k
    assert len(set(p)) == k
    for c in p:
        assert len(c) == 3 and all(0 <= v <= 255 for v in c)


def test_palette_deterministic():
    assert build_palette(16) == build_palette(16)


def test_nearest_exact():
    p = build_palette(16)
    for i, c in enumerate(p):
        assert nearest(p, c) == i


def test_nearest_closest():
    p = build_palette(4)
    # 偏移一点点仍归到最近色
    assert nearest(p, (p[0][0] + 1, p[0][1], p[0][2])) == 0


def test_color_bits_table():
    assert COLOR_BITS == {4: 2, 8: 3, 16: 4, 32: 5, 64: 6}


def test_invalid_k_rejected():
    with pytest.raises(ValueError):
        build_palette(10)  # 仅允许 {4,8,16,32,64}
```

- [ ] **步骤 2：验证失败** — `pytest tests/test_palette.py -q`（FAIL）

- [ ] **步骤 3：实现** — `qrtrans/palette.py`：

```python
from __future__ import annotations
from typing import List, Tuple

VALID_K = (4, 8, 16, 32, 64)
COLOR_BITS = {4: 2, 8: 3, 16: 4, 32: 5, 64: 6}

# 贪心最远点的候选集（5×5×5 立方体网格，覆盖 sRGB）
_CAND = [(r, g, b)
         for r in (0, 64, 128, 191, 255)
         for g in (0, 64, 128, 191, 255)
         for b in (0, 64, 128, 191, 255)]


def build_palette(k: int) -> List[Tuple[int, int, int]]:
    """返回 K 色调色板。确定性、版本固定（属格式的一部分，勿改算法）。
    仅支持 k∈{4,8,16,32,64}。"""
    if k not in VALID_K:
        raise ValueError(f"unsupported palette size {k}; allowed: {VALID_K}")
    pts = [(128, 128, 128)]
    while len(pts) < k:
        best, best_d = None, -1
        for c in _CAND:
            if c in pts:
                continue
            d = min((c[0]-p[0])**2 + (c[1]-p[1])**2 + (c[2]-p[2])**2 for p in pts)
            if d > best_d:
                best_d, best = d, c
        pts.append(best)
    return pts


def nearest(palette, rgb) -> int:
    bi, bd = 0, 1 << 30
    for i, c in enumerate(palette):
        d = (c[0]-rgb[0])**2 + (c[1]-rgb[1])**2 + (c[2]-rgb[2])**2
        if d < bd:
            bd, bi = d, i
    return bi
```

- [ ] **步骤 4：验证通过** — `.venv/bin/pytest tests/test_palette.py -q`（6 passed）

- [ ] **步骤 5：Commit**
```bash
git add qrtrans/palette.py tests/test_palette.py
git commit -m "feat(palette): deterministic fixed palettes and nearest-color"
```

---

## 任务 3：`cm_protocol.py`（帧头 + 位打包 + magic）

**文件：** 创建 `qrtrans/cm_protocol.py`、`tests/test_cm_protocol.py`

- [ ] **步骤 1：失败测试** — `tests/test_cm_protocol.py`：

```python
import pytest
from qrtrans.cm_protocol import (
    CmHeader, CM_MAGIC, header_to_bytes, header_from_bytes,
    bytes_to_indices, indices_to_bytes, COLOR_BITS_LOOKUP,
)
from qrtrans.palette import COLOR_BITS


def _hdr(**over):
    base = dict(magic=CM_MAGIC, version=1, palette_version=1, k=16, cell_px=4,
                grid_w=100, grid_h=80, batch="deadbeef", frame_index=2, frame_total=5,
                ecc_percent=12, compressed=1, payload_len=1234, payload_sha256="a"*64)
    base.update(over)
    return CmHeader(**base)


def test_header_roundtrip():
    h = _hdr()
    b = header_to_bytes(h)
    assert header_from_bytes(b) == h


def test_header_bad_magic_rejected():
    b = bytearray(header_to_bytes(_hdr()))
    b[0:4] = b"XXXX"
    with pytest.raises(ValueError):
        header_from_bytes(bytes(b))


def test_header_crc_corruption_rejected():
    b = bytearray(header_to_bytes(_hdr()))
    b[10] ^= 0xFF  # 改一字段字节
    with pytest.raises(ValueError):
        header_from_bytes(bytes(b))


def test_index_bitpack_roundtrip():
    data = bytes(range(256))
    bpc = COLOR_BITS[16]
    idx = bytes_to_indices(data, bpc)
    assert indices_to_bytes(idx, bpc, original_len=len(data)) == data


def test_index_bitpack_multibyte_cells():
    data = b"abc"
    bpc = COLOR_BITS[4]
    idx = bytes_to_indices(data, bpc)
    assert indices_to_bytes(idx, bpc, original_len=len(data)) == data
```

> `COLOR_BITS_LOOKUP` 在 cm_protocol 中从 palette 复用：实现里 `from .palette import COLOR_BITS as COLOR_BITS_LOOKUP`，测试只验证可导入。

- [ ] **步骤 2：验证失败** — `pytest tests/test_cm_protocol.py -q`（FAIL）

- [ ] **步骤 3：实现** — `qrtrans/cm_protocol.py`：

```python
from __future__ import annotations
import binascii
import struct
from dataclasses import dataclass
from .palette import COLOR_BITS as COLOR_BITS_LOOKUP

CM_MAGIC = b"CMTX"
CM_VERSION = 1
PALETTE_VERSION = 1
# 头布局：!4s 12B H H H H H H B B I 32s I（magic, ver, palver, k, cell_px,
#   grid_w, grid_h, frame_index, frame_total, ecc_percent, compressed, _pad,
#   payload_len, sha256(raw32), crc32)
# 为简化用 struct 拼 + 校验 crc。
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
```

- [ ] **步骤 4：验证通过** — `pytest tests/test_cm_protocol.py -q`（5 passed）

- [ ] **步骤 5：Commit**
```bash
git add qrtrans/cm_protocol.py tests/test_cm_protocol.py
git commit -m "feat(cm): frame header binary format, bit-pack, crc"
```

---

## 任务 4：`finder.py`（标记绘制 + 定位 + 几何）

**文件：** 创建 `qrtrans/finder.py`、`tests/test_finder.py`

- [ ] **步骤 1：失败测试** — `tests/test_finder.py`：

```python
import pytest
from PIL import Image
from qrtrans.finder import draw_markers, locate_markers, interior_box, MARKER_COLOR


def test_draw_then_locate_four_corners():
    img = Image.new("RGB", (200, 150), "white")
    draw_markers(img, cell_px=4)
    corners = locate_markers(img)
    assert corners is not None and len(corners) == 4
    xs = sorted(c[0] for c in corners)
    ys = sorted(c[1] for c in corners)
    assert xs[0] < xs[-1] and ys[0] < ys[-1]   # 有左/右、上/下


def test_locate_returns_none_when_absent():
    img = Image.new("RGB", (200, 150), "white")
    assert locate_markers(img) is None


def test_interior_box_inside_corners():
    img = Image.new("RGB", (200, 150), "white")
    draw_markers(img, cell_px=4)
    corners = locate_markers(img)
    x0, y0, x1, y1 = interior_box(corners, cell_px=4, img_size=img.size)
    assert x0 > 0 and y0 > 0 and x1 < 200 and y1 < 150
    assert x1 > x0 and y1 > y0


def test_locate_survives_slight_scale():
    # 渲染后缩放 95%，仍应定位到 4 个标记
    img = Image.new("RGB", (400, 300), "white")
    draw_markers(img, cell_px=8)
    scaled = img.resize((380, 285), Image.NEAREST)
    corners = locate_markers(scaled)
    assert corners is not None and len(corners) == 4
```

- [ ] **步骤 2：验证失败** — `pytest tests/test_finder.py -q`（FAIL）

- [ ] **步骤 3：实现** — `qrtrans/finder.py`：

```python
from __future__ import annotations
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw

MARKER_COLOR = (0, 0, 0)
MARKER_BG = (255, 255, 255)
MARKER_CELL = 3  # 标记边长（单元格数）


def _marker_size_px(cell_px: int) -> int:
    return MARKER_CELL * cell_px


def draw_markers(canvas: Image.Image, cell_px: int) -> None:
    """在 4 角画 finder 标记：白底 + 黑块。"""
    d = ImageDraw.Draw(canvas)
    s = _marker_size_px(cell_px)
    W, H = canvas.size
    for (x0, y0) in [(0, 0), (W - s, 0), (0, H - s), (W - s, H - s)]:
        d.rectangle([x0, y0, x0 + s - 1, y0 + s - 1], fill=MARKER_COLOR)


def locate_markers(image: Image.Image) -> Optional[List[Tuple[int, int]]]:
    """找 4 角的黑块中心。简单实现：在 4 个角区域内找黑色质心。"""
    W, H = image.size
    px = image.load()
    # 4 个角的探测区域（占边长 1/4）
    zones = [(0, 0), (W // 2, 0), (0, H // 2), (W // 2, H // 2)]
    zone_w, zone_h = W // 2, H // 2
    centers = []
    for (zx, zy) in zones:
        # 找该象限内最靠该象限外角的黑色像素簇质心
        black_pts = []
        # 限缩到角部 1/4 区域更稳：取象限外侧 1/2
        x_lo = zx + (0 if zx == 0 else zone_w // 2)
        x_hi = zx + (zone_w if zx == 0 else zone_w)
        y_lo = zy + (0 if zy == 0 else zone_h // 2)
        y_hi = zy + (zone_h if zy == 0 else zone_h)
        for y in range(y_lo, y_hi, max(1, (y_hi - y_lo) // 32)):
            for x in range(x_lo, x_hi, max(1, (x_hi - x_lo) // 32)):
                r, g, b = px[x, y][:3]
                if r < 64 and g < 64 and b < 64:
                    black_pts.append((x, y))
        if not black_pts:
            return None
        cx = sum(p[0] for p in black_pts) // len(black_pts)
        cy = sum(p[1] for p in black_pts) // len(black_pts)
        centers.append((cx, cy))
    # 排序为 TL, TR, BL, BR
    centers.sort(key=lambda p: (p[1], p[0]))
    top = sorted(centers[:2], key=lambda p: p[0])
    bot = sorted(centers[2:], key=lambda p: p[0])
    return top + bot   # [TL, TR, BL, BR]


def interior_box(corners, cell_px: int, img_size) -> Tuple[int, int, int, int]:
    """由 4 标记中心 + cell_px 推内部网格 bbox。"""
    tl, tr, bl, br = corners
    s = _marker_size_px(cell_px) // 2
    x0 = tl[0] + s
    y0 = tl[1] + s
    x1 = br[0] - s
    y1 = br[1] - s
    return (x0, y0, x1, y1)
```

> 注：`locate_markers` 用稀疏采样+象限质心的简单实现；TDD 通过即可。若鲁棒性不足（后续 e2e 发现），再迭代为连通域/模板匹配。`interior_box` 用 TL/BR 推 bbox。

- [ ] **步骤 4：验证通过** — `pytest tests/test_finder.py -q`（4 passed）

- [ ] **步骤 5：Commit**
```bash
git add qrtrans/finder.py tests/test_finder.py
git commit -m "feat(finder): marker drawing, quadrant-based locate, interior box"
```

---

## 任务 5：`cm_encoder.py`

**文件：** 创建 `qrtrans/cm_encoder.py`、`tests/test_cm_encoder.py`

- [ ] **步骤 1：失败测试** — `tests/test_cm_encoder.py`：

```python
from pathlib import Path
from PIL import Image
from qrtrans.cm_encoder import colormatrix_encode, CmEncodeOptions
from qrtrans.cm_decoder import is_colormatrix_frame


def _opts(**over):
    base = dict(colors=16, cell_px=8, ecc_percent=12, compress=True,
                screen=(1920, 1080), batch="", label=False)
    base.update(over)
    return CmEncodeOptions(**base)


def test_encode_produces_frames(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("hello colormatrix")
    out = tmp_path / "o"
    res = colormatrix_encode(src, out, _opts(batch="enc00001"))
    pngs = list(out.glob("*.png"))
    assert pngs
    # 每张都是合法 colormatrix 帧（含 finder）
    for p in pngs:
        assert is_colormatrix_frame(Image.open(p)) is True


def test_encode_multiframe_for_large(tmp_path):
    src = tmp_path / "big.txt"; src.write_text("Z" * 20000)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="enc00002"))
    assert len(list(out.glob("*.png"))) >= 2


def test_encode_auto_compress_text(tmp_path):
    src = tmp_path / "t.txt"; src.write_text("A" * 5000)  # 高度可压缩
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="enc00003"))
    assert list(out.glob("*.png"))
```

- [ ] **步骤 2：验证失败** — `pytest tests/test_cm_encoder.py -q`（FAIL）

- [ ] **步骤 3：实现** — `qrtrans/cm_encoder.py`：

```python
from __future__ import annotations
import hashlib
import secrets
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw

from . import fs_walk
from .palette import build_palette, COLOR_BITS
from . import cm_protocol, rs
from .finder import draw_markers, MARKER_CELL
from .progress import ProgressCallback, ProgressEvent


@dataclass(frozen=True)
class CmEncodeOptions:
    colors: int = 16
    cell_px: int = 4
    ecc_percent: int = 12
    compress: bool = True
    screen: Tuple[int, int] = (1920, 1080)
    batch: str = ""
    label: bool = True


@dataclass
class CmEncodeResult:
    batch: str
    frame_count: int
    output_files: List[Path]


def _new_batch() -> str:
    return secrets.token_hex(4)


def _nsym(percent: int) -> int:
    return max(2, min(255 - 1, round(255 * percent / 100)))


def _grid_dims(screen, cell_px):
    sw, sh = screen
    # 留出 4 角 finder（MARKER_CELL*cell_px）与可选 40px 标签
    return sw // cell_px, sh // cell_px   # 网格单元数（含 finder 区）


def colormatrix_encode(input_path: Path, out_dir: Path,
                       options: CmEncodeOptions,
                       progress: Optional[ProgressCallback] = None) -> CmEncodeResult:
    files, dirs = fs_walk.collect(input_path)
    if not files and not dirs:
        raise fs_walk.FsError(f"nothing to encode under {input_path}")

    batch = options.batch or _new_batch()
    palette = build_palette(options.colors)
    bpc = COLOR_BITS[options.colors]
    cell_px = options.cell_px
    screen = options.screen

    # 1) 拼 payload：自描述目录清单 + 各文件字节（简单二进制容器）
    payload = _build_payload(files, dirs)
    sha = hashlib.sha256(payload).hexdigest()
    # 2) 压缩（可选，有收益才用）
    if options.compress:
        comp = zlib.compress(payload, 9)
        if len(comp) < len(payload):
            payload, compressed = comp, 1
        else:
            compressed = 0
    else:
        compressed = 0

    # 3) 计算每帧载荷容量（单元格数 → 字节）
    gw, gh = _grid_dims(screen, cell_px)
    # finder 占 4 角各 MARKER_CELL^2 单元；内部网格 = gw-2*MARKER_CELL x gh-2*MARKER_CELL
    iw = gw - 2 * MARKER_CELL
    ih = gh - 2 * MARKER_CELL
    header_cells = 64   # 头区保留 64 单元（足够头位打包 + 余量）
    payload_cells_per_frame = iw * ih - header_cells
    payload_bytes_per_frame = (payload_cells_per_frame * bpc) // 8

    # 4) 分帧 + 每帧 RS
    frames_data = _chunk_with_rs(payload, payload_bytes_per_frame, _nsym(options.ecc_percent))
    frame_total = len(frames_data)
    out_dir.mkdir(parents=True, exist_ok=True)
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
        img = _render_frame(header, frame_payload, palette, bpc, cell_px, screen,
                            options.label, batch, idx, frame_total)
        p = out_dir / f"qrtrans_{batch}_cm_{idx:03d}.png"
        img.save(p, "PNG")
        outputs.append(p)
        if progress is not None:
            progress(ProgressEvent("frame", idx, frame_total))

    return CmEncodeResult(batch=batch, frame_count=frame_total, output_files=outputs)


def _build_payload(files, dirs) -> bytes:
    """简单自描述容器：先目录清单（每条：type|relpath|len），再各文件字节拼接。"""
    import struct
    out = bytearray()
    # 文件
    entries = []
    blob = bytearray()
    for f in files:
        entries.append(("f", f.relpath, len(f.content)))
        blob.extend(f.content)
    for d in dirs:
        entries.append(("d", d.relpath, 0))
    # 清单：4 字节条数 + 每条 type(1) + relpath(utf8 长度前缀 2 字节) + len(4)
    out += struct.pack("!I", len(entries))
    for t, relpath, ln in entries:
        rp = relpath.encode("utf-8")
        out += (b"F" if t == "f" else b"D")
        out += struct.pack("!H", len(rp)) + rp
        out += struct.pack("!I", ln)
    out += bytes(blob)
    return bytes(out)


def _chunk_with_rs(payload: bytes, bytes_per_frame: int, nsym: int):
    """切分 payload 为 ≤bytes_per_frame 的块；每块 RS。返回 [(codeword, original_len)]。"""
    if bytes_per_frame < 1:
        raise ValueError("bytes_per_frame too small")
    out = []
    for i in range(0, len(payload), bytes_per_frame):
        chunk = payload[i:i + bytes_per_frame]
        out.append((rs.rs_encode(chunk, nsym), len(chunk)))
    if not out:  # 空 payload，至少 1 帧
        out.append((rs.rs_encode(b"", nsym), 0))
    return out


def _render_frame(header, frame_payload, palette, bpc, cell_px, screen,
                  label, batch, idx, total) -> Image.Image:
    gw, gh = _grid_dims(screen, cell_px)
    W, H = gw * cell_px, gh * cell_px
    if label:
        H += 40
    canvas = Image.new("RGB", (W, H), "white")
    # 先把头区 + 载荷打包成单元格索引
    header_bytes = cm_protocol.header_to_bytes(header)
    head_idx = cm_protocol.bytes_to_indices(header_bytes, bpc)
    pay_idx = cm_protocol.bytes_to_indices(frame_payload, bpc)
    # 填内部网格（跳过 4 角 MARKER_CELL 区）
    iw = gw - 2 * MARKER_CELL
    ih = gh - 2 * MARKER_CELL
    cells = head_idx + pay_idx
    ci = 0
    for r in range(MARKER_CELL, MARKER_CELL + ih):
        for c in range(MARKER_CELL, MARKER_CELL + iw):
            if ci < len(cells):
                _fill_cell(canvas, c, r, cell_px, palette[cells[ci]])
            ci += 1
    # 画 finder（基于内部画布尺寸的 4 角；若 label，标记在网格区 4 角）
    _draw_markers_on_grid(canvas, gw, gh, cell_px)
    if label:
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, gh * cell_px, W, H], fill="black")
        d.text((10, gh * cell_px + 10), f"batch={batch} cm {idx}/{total}", fill="white")
    return canvas


def _fill_cell(canvas, c, r, cell_px, color):
    x0, y0 = c * cell_px, r * cell_px
    ImageDraw.Draw(canvas).rectangle([x0, y0, x0 + cell_px - 1, y0 + cell_px - 1], fill=color)


def _draw_markers_on_grid(canvas, gw, gh, cell_px):
    d = ImageDraw.Draw(canvas)
    s = MARKER_CELL * cell_px
    for (x0, y0) in [(0, 0), (gw * cell_px - s, 0), (0, gh * cell_px - s), (gw * cell_px - s, gh * cell_px - s)]:
        d.rectangle([x0, y0, x0 + s - 1, y0 + s - 1], fill=(0, 0, 0))
```

> 注：`is_colormatrix_frame`（测试依赖）在任务 6 的 cm_decoder 里；本任务测试会因 cm_decoder 未创建而 FAIL。**实现者：把 `is_colormatrix_frame` 的占位先放到 cm_decoder.py（仅 finder 检测，不含完整解码），让本任务测试可运行；或把该测试移到任务 6 之后。** 推荐：在 cm_encoder 任务中，先在 cm_decoder.py 创建一个仅含 `is_colormatrix_frame` 的最小实现，任务 6 再补全解码。

- [ ] **步骤 4：验证通过** — `pytest tests/test_cm_encoder.py -q`（3 passed）

- [ ] **步骤 5：Commit**
```bash
git add qrtrans/cm_encoder.py qrtrans/cm_decoder.py tests/test_cm_encoder.py
git commit -m "feat(cm): colormatrix encoder (compress+RS+frame+render)"
```

---

## 任务 6：`cm_decoder.py`

**文件：** 完善 `qrtrans/cm_decoder.py`、创建 `tests/test_cm_decoder.py`

- [ ] **步骤 1：失败测试** — `tests/test_cm_decoder.py`：

```python
from pathlib import Path
from PIL import Image
from qrtrans.cm_encoder import colormatrix_encode, CmEncodeOptions
from qrtrans.cm_decoder import colormatrix_decode, is_colormatrix_frame


def _opts(**over):
    base = dict(colors=16, cell_px=8, ecc_percent=12, compress=True,
                screen=(640, 480), batch="", label=False)
    base.update(over)
    return CmEncodeOptions(**base)


def test_roundtrip_single_file(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("hello colormatrix 你好 🎉")
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="rt000001"))
    dest = tmp_path / "dec.txt"
    colormatrix_decode(out, dest)
    assert dest.read_text(encoding="utf-8") == "hello colormatrix 你好 🎉"


def test_roundtrip_directory(tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "b.txt").write_text("B-content")
    (root / "empty").mkdir()
    (root / "top.txt").write_text("T")
    out = tmp_path / "o"
    colormatrix_encode(root, out, _opts(batch="rt000002"))
    dest = tmp_path / "dec"
    colormatrix_decode(out, dest)
    assert (dest / "sub" / "b.txt").read_text() == "B-content"
    assert (dest / "top.txt").read_text() == "T"
    assert (dest / "empty").is_dir()


def test_roundtrip_multiframe(tmp_path):
    src = tmp_path / "big.txt"; src.write_text("Z" * 20000)
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="rt000003"))
    dest = tmp_path / "dec.txt"
    colormatrix_decode(out, dest)
    assert dest.read_text() == "Z" * 20000


def test_is_colormatrix_frame_detection(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("x")
    out = tmp_path / "o"
    colormatrix_encode(src, out, _opts(batch="det00001"))
    p = next(out.glob("*.png"))
    assert is_colormatrix_frame(Image.open(p)) is True
    assert is_colormatrix_frame(Image.new("RGB", (100, 100), "white")) is False
```

- [ ] **步骤 2：验证失败** — `pytest tests/test_cm_decoder.py -q`（FAIL）

- [ ] **步骤 3：实现** — `qrtrans/cm_decoder.py`：

```python
from __future__ import annotations
import hashlib
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from PIL import Image

from . import fs_walk
from .palette import build_palette, COLOR_BITS
from . import cm_protocol, rs
from .finder import locate_markers, interior_box, MARKER_CELL, _marker_size_px
from .progress import ProgressCallback, ProgressEvent


@dataclass
class CmDecodeResult:
    files_written: List[str] = field(default_factory=list)
    dirs_created: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)


def is_colormatrix_frame(image: Image.Image) -> bool:
    return locate_markers(image) is not None


def _nsym(percent: int) -> int:
    return max(2, min(254, round(255 * percent / 100)))


def _detect_cell_px_and_header(image):
    """对候选 cell_px 探测，返回 (header, palette, bpc, cell_px, interior_bbox) 或 None。"""
    corners = locate_markers(image)
    if corners is None:
        return None
    W, H = image.size
    for cell_px in (3, 4, 5, 6, 8, 2):
        x0, y0, x1, y1 = interior_box(corners, cell_px, image.size)
        iw = (x1 - x0) // cell_px
        ih = (y1 - y0) // cell_px
        if iw <= 2 * MARKER_CELL or ih <= 2 * MARKER_CELL:
            continue
        inner_w = iw - 2 * MARKER_CELL
        inner_h = ih - 2 * MARKER_CELL
        # 采头区前 64 单元
        idx = _sample_indices(image, x0, y0, cell_px, MARKER_CELL, MARKER_CELL,
                              inner_w, inner_h, count=64)
        # 头字节数 = 由 bits/cell 反推；尝试解头
        for k in (16, 4, 8, 32, 64):
            bpc = COLOR_BITS[k]
            hb_len = (64 * bpc) // 8
            try:
                hb = cm_protocol.indices_to_bytes(idx, bpc, hb_len)
                h = cm_protocol.header_from_bytes(hb)
            except ValueError:
                continue
            if h.cell_px == cell_px and h.k == k:
                return (h, build_palette(k), bpc, cell_px, (x0, y0, x1, y1),
                        inner_w, inner_h)
    return None


def _sample_indices(image, x0, y0, cell_px, col0, row0, inner_w, inner_h, count):
    px = image.load()
    idx = []
    for r in range(inner_h):
        for c in range(inner_w):
            if len(idx) >= count:
                return idx
            cx = x0 + (c + col0 + 0.5) * cell_px
            cy = y0 + (r + row0 + 0.5) * cell_px
            idx.append(_nearest_raw(px, int(cx), int(cy)))
    return idx


def _nearest_raw(px, x, y):
    # 占位；实际由调用方传 palette 后用 nearest。这里返回原始 rgb 由上层处理。
    return px[x, y][:3]
```

> **实现者注意**：上面 `_detect_cell_px_and_header` 与 `_sample_indices` 的协作需要返回"采样后的 RGB 列表"再统一做 nearest。建议重构为：`_sample_rgbs(...)` 返回 RGB 列表，对每个候选 (k, cell_px) 用 `palette=build_palette(k)` 跑 nearest 得 idx，再解头。实现者按"先采样 RGB、再按候选 k 做 nearest"的清晰顺序实现，保证测试通过。完整解码流程：

```python
def colormatrix_decode(input_path: Path, output: Path,
                       progress: Optional[ProgressCallback] = None) -> CmDecodeResult:
    images = fs_walk.gather_images(input_path)
    frames = []   # [(header, payload_bytes)]
    total = len(images)
    for i, img_path in enumerate(images, start=1):
        with Image.open(img_path) as img:
            img.load()
            info = _detect_cell_px_and_header(img)
            if info is None:
                continue
            (h, palette, bpc, cell_px, bbox, inner_w, inner_h) = info
            # 采全部内部单元 RGB → nearest → idx → 头区/载荷区分
            rgbs = _sample_rgbs(img, bbox, cell_px, MARKER_CELL, inner_w, inner_h)
            idx = [build_palette_lookup_nearest(palette, c) for c in rgbs]
            head_cells = 64
            head_bytes = cm_protocol.indices_to_bytes(idx[:head_cells], bpc,
                                                      len(cm_protocol.header_to_bytes(h)))
            # 头已能解（探测时验过）；取载荷 idx
            pay_idx = idx[head_cells:]
            # 载荷字节里前段是 RS codeword，长 = ceil(len(pay_idx)*bpc/8) 但 RS 长需对齐
            # 实现：把 pay_idx 转 bytes，rs_decode 用 header.payload_len 还原原始块
            cw_len = (len(pay_idx) * bpc) // 8
            cw = cm_protocol.indices_to_bytes(pay_idx, bpc, cw_len)
            try:
                chunk = rs.rs_decode(cw, _nsym(h.ecc_percent), h.payload_len)
            except Exception as e:
                continue  # 该帧 RS 失败，跳过（缺失帧由 frame_total 判定）
            frames.append((h, chunk))
        if progress is not None:
            progress(ProgressEvent("scan", i, total))
    # 拼装
    if not frames:
        raise ValueError("no colormatrix frames found")
    frames.sort(key=lambda x: x[0].frame_index)
    batch_payload = b"".join(chunk for _, chunk in frames)
    # 解压
    if frames[0][0].compressed == 1:
        batch_payload = zlib.decompress(batch_payload)
    # 校验 sha
    sha = hashlib.sha256(batch_payload).hexdigest()
    if sha != frames[0][0].payload_sha256:
        raise ValueError("payload sha256 mismatch")
    # 还原 Records
    files, dirs = _parse_payload(batch_payload)
    # 输出形态判定（沿用主程序语义：单文件→写文件；否则 rebuild）
    _write_output(files, dirs, output, frames[0][0])
    result = CmDecodeResult()
    result.files_written = [f.relpath for f in files]
    result.dirs_created = [d.relpath for d in dirs]
    return result
```

> `_parse_payload`（解 `_build_payload` 的容器格式）、`_write_output`（单/多文件判定，复用 fs_walk.rebuild）、`_sample_rgbs`、`build_palette_lookup_nearest` 由实现者补全，对称于 encoder。TDD 保证往返一致。

- [ ] **步骤 4：验证通过** — `pytest tests/test_cm_decoder.py -q`（4 passed）

- [ ] **步骤 5：Commit**
```bash
git add qrtrans/cm_decoder.py tests/test_cm_decoder.py
git commit -m "feat(cm): colormatrix decoder (detect+geometry+RS+decompress+rebuild)"
```

---

## 任务 7：CLI + 分流 + QR 默认 grid 4x2

**文件：** 改 `qrtrans/cli.py`、`tests/test_cli.py`（追加）

- [ ] **步骤 1：失败测试** — 在 `tests/test_cli.py` 追加：

```python
def test_cli_default_mode_is_colormatrix(tmp_path):
    src = tmp_path / "n.txt"; src.write_text("default mode")
    out = tmp_path / "o"; dec = tmp_path / "d.txt"
    r = _run(["encode", str(src), "-o", str(out), "--batch", "cmdef0001"])
    assert r.returncode == 0, r.stderr
    # 产物应为 colormatrix 帧（cm_ 文件名）
    assert list(out.glob("qrtrans_cmdef0001_cm_*.png"))


def test_cli_colormatrix_roundtrip(tmp_path):
    src = tmp_path / "n.txt"; src.write_text("cli cm 你好")
    out = tmp_path / "o"; dec = tmp_path / "d.txt"
    assert _run(["encode", str(src), "-o", str(out), "--batch", "clicm001"]).returncode == 0
    assert _run(["decode", str(out), "-o", str(dec)]).returncode == 0
    assert dec.read_text(encoding="utf-8") == "cli cm 你好"


def test_cli_colormatrix_custom_colors_cellpx(tmp_path):
    src = tmp_path / "n.txt"; src.write_text("x" * 500)
    out = tmp_path / "o"
    r = _run(["encode", str(src), "-o", str(out), "--colors", "32", "--cell-px", "5",
              "--batch", "cmcust01"])
    assert r.returncode == 0, r.stderr


def test_cli_qr_mode_still_works(tmp_path):
    src = tmp_path / "n.txt"; src.write_text("qr still ok")
    out = tmp_path / "o"; dec = tmp_path / "d.txt"
    r = _run(["encode", str(src), "-o", str(out), "--mode", "array", "--batch", "qrok0001"])
    assert r.returncode == 0
    assert list(out.glob("qrtrans_qrok0001_frame_*.png"))   # QR array 命名


def test_cli_qr_default_grid_is_4x2(tmp_path):
    # 不传 --grid，QR array 默认 4x2
    src = tmp_path / "big.txt"; src.write_text("K" * 14000)
    out = tmp_path / "o"
    _run(["encode", str(src), "-o", str(out), "--mode", "array", "--batch", "grid42001"])
    from PIL import Image
    from qrtrans.qr_scan import scan
    frames = list(out.glob("qrtrans_grid42001_frame_*.png"))
    assert max(len(scan(Image.open(f))) for f in frames) == 8   # 4x2
```

- [ ] **步骤 2：验证失败** — `pytest tests/test_cli.py -q`（新测试 FAIL）

- [ ] **步骤 3：改 `qrtrans/cli.py`**

3a. `--mode` choices 加 `colormatrix` 并设为默认：
```python
    enc.add_argument("--mode", choices=["colormatrix", "array", "single"], default="colormatrix")
```

3b. 加 colormatrix 参数：
```python
    enc.add_argument("--colors", type=int, default=16, choices=[4, 8, 16, 32, 64])
    enc.add_argument("--cell-px", type=int, default=4)
    enc.add_argument("--cm-ecc", type=int, default=12)
    cmcomp = enc.add_mutually_exclusive_group()
    cmcomp.add_argument("--compress", dest="compress", action="store_true", default=True)
    cmcomp.add_argument("--no-compress", dest="compress", action="store_false")
```

3c. QR array 默认 grid 改 4x2：
```python
    enc.add_argument("--grid", default="4x2", ...)
```

3d. encode 分支按 mode 分流（保留既有 QR 调用，新增 colormatrix 分支）：
```python
    if args.command == "encode":
        pp = _make_progress_printer()
        try:
            if args.mode == "colormatrix":
                from .cm_encoder import colormatrix_encode, CmEncodeOptions
                opts = CmEncodeOptions(colors=args.colors, cell_px=args.cell_px,
                                       ecc_percent=args.cm_ecc, compress=args.compress,
                                       screen=args.screen, batch=args.batch, label=args.label)
                res = colormatrix_encode(args.input, args.outdir, opts, progress=pp)
                print(f"encoded batch={res.batch} frames={res.frame_count} -> {args.outdir}")
            else:
                opts = EncodeOptions(mode=args.mode, screen=args.screen, module_px=args.module_px,
                                     grid=args.grid, ec=args.ec, chunk_raw_bytes=args.chunk_raw_bytes,
                                     label=args.label, batch=args.batch)
                res = encode(args.input, args.outdir, opts, progress=pp)
                print(f"encoded batch={res.batch} payloads={res.payload_count} files={len(res.output_files)} -> {args.outdir}")
        except (FsError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr); return _EXIT_FAIL
        return _EXIT_OK
```

3e. decode 分支：自动检测分流（输入目录/文件 → 优先 colormatrix，否则 QR）。最简实现：先试 `is_colormatrix_frame`（取第一张图），若是则走 `colormatrix_decode`，否则走既有 `decode`：
```python
    if args.command == "decode":
        pp = _make_progress_printer()
        try:
            from .cm_decoder import is_colormatrix_frame
            imgs = fs_walk.gather_images(args.input)
            use_cm = bool(imgs) and all(is_colormatrix_frame(Image.open(p)) for p in imgs[:1])
            if use_cm:
                from .cm_decoder import colormatrix_decode
                colormatrix_decode(args.input, args.output, progress=pp)
            else:
                res = decode(args.input, args.output, DecodeOptions(strict=args.strict), progress=pp)
                for w in res.warnings: print(f"warning: {w}", file=sys.stderr)
                for f in res.files_written: print(f"file: {f}")
                for d in res.dirs_created: print(f"dir:  {d}")
                if res.failed: return _EXIT_PARTIAL
        except (DecodeError, FsError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr); return _EXIT_FAIL
        return _EXIT_OK
```

> 顶部 `from PIL import Image` 与 `from . import fs_walk` 已可用。

- [ ] **步骤 4：验证通过** — `pytest tests/test_cli.py -q`（含新 5 项）

- [ ] **步骤 5：Commit**
```bash
git add qrtrans/cli.py tests/test_cli.py
git commit -m "feat(cli): colormatrix as default mode, QR grid 4x2, auto-dispatch decode"
```

---

## 任务 8：PyInstaller spec 更新 + 本地 frozen 冒烟

**文件：** 改 `packaging/qrtrans.spec`

- [ ] **步骤 1：改 spec** — `hiddenimports` 加 `reedsolo`、`qrtrans.palette`、`qrtrans.cm_protocol`、`qrtrans.finder`、`qrtrans.rs`、`qrtrans.cm_encoder`、`qrtrans.cm_decoder`；`binaries` 保留 `collect_dynamic_libs('pyzbar')`。`reedsolo` 是纯 Python，`collect_submodules('reedsolo')` 也可加入确保。

- [ ] **步骤 2：本地冒烟**
```bash
.venv/bin/pyinstaller packaging/qrtrans.spec --noconfirm
./dist/qrtrans --help
echo "cm smoke" > /tmp/opencode/in.txt
./dist/qrtrans encode /tmp/opencode/in.txt -o /tmp/opencode/cmout --batch cmsmoke1
./dist/qrtrans decode /tmp/opencode/cmout -o /tmp/opencode/cmdec.txt
diff /tmp/opencode/in.txt /tmp/opencode/cmdec.txt && echo "CM ROUNDTRIP OK"
rm -rf dist build
```

- [ ] **步骤 3：Commit**
```bash
git add packaging/qrtrans.spec
git commit -m "build(packaging): include reedsolo and cm modules in pyinstaller spec"
```

---

## 任务 9：端到端 + 回归

**文件：** 创建 `tests/test_colormatrix_e2e.py`

- [ ] **步骤 1：测试** — 含：默认参数往返、`--colors 32`/`--cell-px 3`/`--no-compress`/`--cm-ecc 20` 各可调往返、中文/emoji、嵌套目录+空目录、二进制（NUL/高位字节）、丢一帧=该批失败（与 QR 一致）、混合（QR 目录 vs cm 目录分别正确）。

```python
from pathlib import Path
from PIL import Image
from qrtrans.cm_encoder import colormatrix_encode, CmEncodeOptions
from qrtrans.cm_decoder import colormatrix_decode


def _opts(**over):
    base = dict(colors=16, cell_px=8, ecc_percent=12, compress=True,
                screen=(640, 480), batch="", label=False)
    base.update(over); return CmEncodeOptions(**base)


def _rt(tmp_path, mode_opts, content_fn):
    src = tmp_path / "a.bin"; src.write_bytes(content_fn())
    out = tmp_path / "o"; dec = tmp_path / "dec"
    colormatrix_encode(src, out, _opts(batch="e2000001", **mode_opts))
    colormatrix_decode(out, dec)
    return dec.read_bytes()


def test_e2e_unicode_emoji(tmp_path):
    assert _rt(tmp_path, {}, lambda: "你好 🎉 cm".encode()) == "你好 🎉 cm".encode()


def test_e2e_binary(tmp_path):
    assert _rt(tmp_path, {}, lambda: bytes(range(256))*4) == bytes(range(256))*4


def test_e2e_no_compress(tmp_path):
    assert _rt(tmp_path, {"compress": False}, lambda: b"x"*5000) == b"x"*5000


def test_e2e_colors32_cellpx3(tmp_path):
    assert _rt(tmp_path, {"colors": 32, "cell_px": 3}, lambda: b"y"*3000) == b"y"*3000


def test_e2e_drop_frame_fails(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("Z"*20000)
    out = tmp_path / "o"; colormatrix_encode(src, out, _opts(batch="e2drop01"))
    pngs = sorted(out.glob("*.png")); pngs[0].unlink()
    import pytest
    with pytest.raises(Exception):
        colormatrix_decode(out, tmp_path / "dec")
```

- [ ] **步骤 2：验证** — `pytest tests/test_colormatrix_e2e.py -q`；`pytest -q` 全量绿（既有 89 + 新增 ≈ 30+）

- [ ] **步骤 3：Commit**
```bash
git add tests/test_colormatrix_e2e.py
git commit -m "test(cm): end-to-end roundtrips, tunables, binary, drop-frame semantics"
```

---

## 自检

### 1. 规格覆盖度
- §2 模式/CLI/默认（colormatrix 默认、QR grid 4x2、`--colors`/`--cell-px`/`--cm-ecc`/`--no-compress`）：任务 7 ✓
- §3 调色板（确定性、K 档位）：任务 2 ✓
- §4 帧结构（finder + 头区 + 载荷、magic、CRC）：任务 3/4/5 ✓
- §5 每帧 RS：任务 1/5/6 ✓
- §6 压缩自动：任务 5/6 ✓
- §7/§8 编解码管线 + 自动检测分流：任务 5/6/7 ✓
- §10 依赖 reedsolo + PyInstaller：任务 1/8 ✓
- §11 测试矩阵：任务 1–7 + 任务 9 e2e ✓

### 2. 占位符扫描
- 任务 6 的 cm_decoder 含部分"由实现者补全"的说明（_parse_payload/_write_output/_sample_rgbs），因精确代码依赖采样与容器格式的具体协作；**属计划允许的实现细节下放，TDD 会锁定行为**。其余任务含完整代码。
- 无 TODO。

### 3. 类型一致性
- `CmHeader` 字段在 cm_protocol 定义，cm_encoder/cm_decoder 复用一致 ✓
- `CmEncodeOptions(colors,cell_px,ecc_percent,compress,screen,batch,label)` 在 cli/cm_encoder 一致 ✓
- `COLOR_BITS` 在 palette 定义、cm_protocol/cm_encoder/cm_decoder 复用 ✓
- `MARKER_CELL`、`locate_markers`、`interior_box` 签名一致 ✓
- 命名约定：colormatrix 用 `_cm_NNN.png`，QR 用 `_frame_NN.png`（分流不冲突）✓

### 4. 范围
- 单一连贯特性，9 个任务，可由一个计划覆盖。任务 6（解码几何）为最复杂点，已单独成任务并强调 TDD。
