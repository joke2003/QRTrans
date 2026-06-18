# QRTrans 进度反馈与流式重构 设计规格

- **日期**：2026-06-18
- **状态**：待审查
- **关联**：`docs/superpowers/specs/2026-06-17-qrtrans-design.md`（主程序设计）

---

## 1. 目标与非目标

### 目标
1. 给 encode/decode 增加**可观测的进度反馈**：调用方可注册回调获取结构化进度事件；CLI 默认向 stderr 输出单行刷新进度。
2. **流式重构 array 编码**：把"先全渲染进内存再写帧"改为"按帧渲染→pack→save"，降低峰值内存、让首帧更早落盘、并天然配合进度。

### 非目标（YAGNI）
- 不做 ETA/耗时统计、彩色进度条、tqdm 依赖。
- 不改协议、不改载荷格式；老载荷与老调用方式完全兼容。
- 不引入新的外部依赖。

---

## 2. 进度 API

新建 `qrtrans/progress.py`：

```python
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass(frozen=True)
class ProgressEvent:
    phase: str       # "prepare" | "frame" | "qr" | "scan" | "reassemble"
    current: int
    total: int

ProgressCallback = Callable[[ProgressEvent], None]
```

- `encode()` 与 `decode()` 各新增末位可选参数 `progress: Optional[ProgressCallback] = None`。
- **`progress=None` 时静默**，行为与现状完全一致（向后兼容，现有测试零影响）。
- 调用约定：实现层在每个工作单元完成后调用 `progress(event)`；`event.current` 单调递增，末尾 `current == total`。

---

## 3. encode 改造

### 3.1 array 模式：按帧渲染（流式）
现状（`encoder.py:90-91`）先用列表推导把所有 QR 图像渲染进内存，再分页写帧。改为：

- 对 **payloads 分页**（而非 images）：`payload_frames = paginate(payloads, spec.per_frame)`。
- 逐帧：渲染该帧的 QR → `pack` → `save` → 发 `frame i/N` 事件。

```python
payload_frames = paginate(payloads, spec.per_frame)
total = len(payload_frames)
for idx, frame_payloads in enumerate(payload_frames, start=1):
    images = [qr_render.render(pl, module_px=..., ec=...) for pl in frame_payloads]
    canvas = pack(images, spec, batch=batch, frame_index=idx, frame_total=total)
    canvas.save(out_dir / f"qrtrans_{batch}_frame_{idx:02d}.png", "PNG")
    if progress is not None:
        progress(ProgressEvent("frame", idx, total))
```

收益：峰值内存从"全部 QR 图像"降到"单帧 QR 图像"；首帧更早落盘；天然带进度。

### 3.2 single 模式：逐张渲染+存盘（已是流式，仅加事件）
```python
total = len(payloads)
for i, pl in enumerate(payloads, start=1):
    img = qr_render.render(pl, ...)
    img.save(out_dir / f"qrtrans_{batch}_{i:04d}.png", "PNG")
    if progress is not None:
        progress(ProgressEvent("qr", i, total))
```

### 3.3 prepare 事件
在 payloads 构造完成后、进入输出循环前，发一次 `prepare` 事件告知规模（如 `ProgressEvent("prepare", len(payloads), len(payloads))`），让 UI 能先显示"准备完成：N 个载荷"。

---

## 4. decode 改造

`decode()` 新增 `progress` 参数，两处发事件：

- **scan 阶段**：`gather_images` 后逐张扫描，每张完成发 `scan i/N`（N=图像数）。
- **reassemble 阶段**：按 fid 逐文件重组，每个完成发 `reassemble i/N`（N=文件组数）。

```python
images = fs_walk.gather_images(input_path)
total_imgs = len(images)
payloads = []
for i, img_path in enumerate(images, start=1):
    with Image.open(img_path) as img:
        img.load()
        payloads.extend(qr_scan.scan(img))
    if progress is not None:
        progress(ProgressEvent("scan", i, total_imgs))
# ...分组、重组
total_files = len(file_groups)
for i, (fid, group) in enumerate(file_groups.items(), start=1):
    reassembled.append(_reassemble_file(group))
    if progress is not None:
        progress(ProgressEvent("reassemble", i, total_files))
```

---

## 5. CLI 默认进度

- `cli.py` 实现一个默认 printer，传给 `encode`/`decode`。
- 输出到 **stderr**（保持 stdout 的机器可读输出干净）。
- **tty 模式**（`sys.stderr.isatty()` 为真）：单行刷新
  `\r<标签> <current>/<total> (<pct>%)   `，`current==total` 时换行。
- **非 tty 回退**（重定向到文件等）：只在每个阶段完成（`current==total`）时打一行，避免 `\r` 污染日志。
- phase → 中文标签映射：`prepare→准备`、`frame→写帧`、`qr→生成`、`scan→扫描`、`reassemble→还原`。

---

## 6. 测试与验证

新增 `tests/test_progress.py`：
- 用捕获型 callback（把事件追加到列表）断言：
  - encode array：`prepare` 后接 `frame 1..N`，有序、末尾 `current==total`。
  - encode single：`prepare` 后接 `qr 1..N`。
  - decode：`scan 1..N` 与 `reassemble 1..N`。
- **向后兼容**：`encode(...)` / `decode(...)` 不传 `progress` 时行为与现状一致（既有测试全绿）。
- CLI：subprocess 跑 encode，捕获 stderr，断言含进度子串（如 `写帧`/`%`）。

---

## 7. 影响面

| 文件 | 改动 |
|---|---|
| `qrtrans/progress.py` | 新建：`ProgressEvent`、`ProgressCallback` |
| `qrtrans/encoder.py` | `encode()` 加 `progress` 参数；array 改流式；发 `prepare/frame/qr` |
| `qrtrans/decoder.py` | `decode()` 加 `progress` 参数；发 `scan/reassemble` |
| `qrtrans/cli.py` | 默认 printer + isatty 回退；传给 encode/decode |
| `tests/test_progress.py` | 新建：事件序列 + 兼容性 |

- 协议零改动、依赖零新增。
- 峰值内存下降（array 流式）。
- 既有 79 个测试保持通过。

---

## 8. 未来扩展（不在本次范围）
- ETA 与耗时统计。
- 彩色/多行进度（可日后接 tqdm，回调 API 已为其预留）。
- 更细粒度（如单 QR 内的渲染步骤）——无必要。
