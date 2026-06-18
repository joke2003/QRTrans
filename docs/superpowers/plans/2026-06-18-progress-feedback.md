# QRTrans 进度反馈与流式重构 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 给 encode/decode 加结构化进度回调 + CLI 单行刷新进度；并把 array 编码从"全渲染进内存再写帧"重构为"按帧渲染"流式，降低峰值内存、首帧更早落盘。

**架构：** 新增 `progress.py`（`ProgressEvent`/`ProgressCallback`）；`encode()`/`decode()` 各加可选 `progress` 参数（默认 None=静默，完全向后兼容）；encode 的 array 分支改为按帧渲染；CLI 默认 printer 输出到 stderr、isatty 时单行刷新、非 tty 仅打阶段完成行。

**技术栈：** 纯标准库（dataclasses、typing）。

**参考规格：** `docs/superpowers/specs/2026-06-18-progress-feedback-design.md`

**验证：** `.venv/bin/pytest -q`；CLI 用 subprocess 捕获 stderr 验证进度输出。

---

## 跨模块类型约定

```python
# qrtrans/progress.py
@dataclass(frozen=True)
class ProgressEvent:
    phase: str       # "prepare" | "frame" | "qr" | "scan" | "reassemble"
    current: int
    total: int
ProgressCallback = Callable[[ProgressEvent], None]
```

---

## 任务 1：进度类型 `progress.py`

**文件：** 创建 `qrtrans/progress.py`、`tests/test_progress.py`

- [ ] **步骤 1：编写失败的测试** — `tests/test_progress.py`（先只测类型本身）：

```python
from dataclasses import FrozenInstanceError
import pytest
from qrtrans.progress import ProgressEvent, ProgressCallback


def test_progress_event_fields():
    ev = ProgressEvent(phase="frame", current=3, total=10)
    assert ev.phase == "frame"
    assert ev.current == 3
    assert ev.total == 10


def test_progress_event_is_frozen():
    ev = ProgressEvent(phase="qr", current=1, total=2)
    with pytest.raises(FrozenInstanceError):
        ev.current = 5  # type: ignore


def test_progress_callback_is_callable_type():
    # 仅断言 ProgressCallback 可用作类型注解（typing 回调别名）
    events = []
    cb: ProgressCallback = lambda e: events.append(e)
    cb(ProgressEvent("scan", 1, 1))
    assert events == [ProgressEvent("scan", 1, 1)]
```

- [ ] **步骤 2：运行测试验证失败** — `.venv/bin/pytest tests/test_progress.py -q`（FAIL：模块不存在）

- [ ] **步骤 3：编写实现** — `qrtrans/progress.py`：

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProgressEvent:
    phase: str       # "prepare" | "frame" | "qr" | "scan" | "reassemble"
    current: int
    total: int


ProgressCallback = Callable[[ProgressEvent], None]
```

- [ ] **步骤 4：运行测试验证通过** — `.venv/bin/pytest tests/test_progress.py -q`（3 passed）

- [ ] **步骤 5：Commit**

```bash
git add qrtrans/progress.py tests/test_progress.py
git commit -m "feat: add ProgressEvent and ProgressCallback types"
```

---

## 任务 2：encoder 流式重构 + 进度

**文件：** 修改 `qrtrans/encoder.py`、`tests/test_progress.py`（追加）

- [ ] **步骤 1：追加失败的测试** — 在 `tests/test_progress.py` 末尾追加：

```python
from qrtrans.encoder import encode, EncodeOptions


def _opts(**over):
    base = dict(mode="array", screen=(1920, 1080), module_px=3, grid="3x1",
                ec="M", chunk_raw_bytes=1300, label=True, batch="prog0001")
    base.update(over)
    return EncodeOptions(**base)


def _capture():
    events = []

    def cb(ev):
        events.append(ev)
    return cb, events


def test_encode_array_emits_prepare_then_frames(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("Z" * 4000)  # 4 块 -> 2 帧（per_frame=3）
    cb, events = _capture()
    encode(src, tmp_path / "out", _opts(mode="array", batch="frame001"), progress=cb)
    assert events[0] == ProgressEvent("prepare", 4, 4)
    frames = [e for e in events if e.phase == "frame"]
    assert [(e.current, e.total) for e in frames] == [(1, 2), (2, 2)]


def test_encode_single_emits_qr_events(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("A" * 5000)  # 4 块
    cb, events = _capture()
    encode(src, tmp_path / "out", _opts(mode="single", batch="qrevt001"), progress=cb)
    assert events[0].phase == "prepare"
    qrs = [e for e in events if e.phase == "qr"]
    assert [(e.current, e.total) for e in qrs] == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_encode_without_progress_still_works(tmp_path):
    # 不传 progress：行为与现状一致（向后兼容）
    src = tmp_path / "a.txt"
    src.write_text("hello")
    res = encode(src, tmp_path / "out", _opts(batch="noprog01"))  # progress 默认 None
    assert res.payload_count >= 1
    assert list((tmp_path / "out").glob("*.png"))
```

- [ ] **步骤 2：运行测试验证失败** — `.venv/bin/pytest tests/test_progress.py -q`（新测试 FAIL：encode 不接受 progress 参数）

- [ ] **步骤 3：修改 `qrtrans/encoder.py`**

在顶部 import 增加：
```python
from typing import List, Optional, Tuple
from .progress import ProgressCallback, ProgressEvent
```
（`Optional` 已用于类型注解；若原文件未导入 `Optional` 则一并加。）

把 `encode` 函数整体替换为（array 分支改为**按帧渲染**流式，并发 prepare/frame/qr 事件）：

```python
def encode(
    input_path: Path,
    out_dir: Path,
    options: EncodeOptions,
    progress: Optional[ProgressCallback] = None,
) -> EncodeResult:
    if options.mode not in ("single", "array"):
        raise ValueError(f"bad mode: {options.mode!r}")

    files, dirs = fs_walk.collect(input_path)
    if not files and not dirs:
        raise fs_walk.FsError(f"nothing to encode under {input_path}")

    batch = options.batch or _new_batch_id()
    payloads = _build_payloads(files, dirs, batch, options.chunk_raw_bytes)

    if progress is not None:
        progress(ProgressEvent("prepare", len(payloads), len(payloads)))

    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: List[Path] = []

    if options.mode == "single":
        total = len(payloads)
        for i, pl in enumerate(payloads, start=1):
            img = qr_render.render(pl, module_px=options.module_px, ec=options.ec)
            p = out_dir / f"qrtrans_{batch}_{i:04d}.png"
            img.save(p, "PNG")
            outputs.append(p)
            if progress is not None:
                progress(ProgressEvent("qr", i, total))
    else:
        spec = _resolve_framespec(options)
        payload_frames = paginate(payloads, spec.per_frame)
        total = len(payload_frames)
        for idx, frame_payloads in enumerate(payload_frames, start=1):
            images = [qr_render.render(pl, module_px=options.module_px, ec=options.ec)
                      for pl in frame_payloads]
            canvas = pack(images, spec, batch=batch,
                          frame_index=idx, frame_total=total)
            p = out_dir / f"qrtrans_{batch}_frame_{idx:02d}.png"
            canvas.save(p, "PNG")
            outputs.append(p)
            if progress is not None:
                progress(ProgressEvent("frame", idx, total))

    return EncodeResult(batch=batch, payload_count=len(payloads), output_files=outputs)
```

> 注意：`paginate` 现作用于 payloads 列表（泛型），空 payloads 情形已被前面的 FsError 拦截；行为不变。

- [ ] **步骤 4：运行测试验证通过** — `.venv/bin/pytest tests/test_progress.py -q`（6 passed）

- [ ] **步骤 5：回归** — `.venv/bin/pytest -q`（全部通过，既有 encoder 测试不受影响）

- [ ] **步骤 6：Commit**

```bash
git add qrtrans/encoder.py tests/test_progress.py
git commit -m "feat(encoder): streaming array render + progress callback"
```

---

## 任务 3：decoder 进度

**文件：** 修改 `qrtrans/decoder.py`、`tests/test_progress.py`（追加）

- [ ] **步骤 1：追加失败的测试** — 在 `tests/test_progress.py` 末尾追加：

```python
from qrtrans.decoder import decode, DecodeOptions


def test_decode_emits_scan_and_reassemble(tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("B" * 10)
    (root / "top.txt").write_text("T")
    out = tmp_path / "out"
    encode(root, out, _opts(mode="array", batch="dec000001"))
    cb, events = _capture()
    res = decode(out, tmp_path / "dec", DecodeOptions(), progress=cb)
    scans = [e for e in events if e.phase == "scan"]
    reass = [e for e in events if e.phase == "reassemble"]
    assert scans and scans[-1].current == scans[-1].total
    assert reass and reass[-1].current == reass[-1].total
    assert (tmp_path / "dec" / "top.txt").read_text(encoding="utf-8") == "T"


def test_decode_without_progress_still_works(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hi")
    out = tmp_path / "out"
    encode(src, out, _opts(mode="single", batch="dnp00001"))
    decode(out, tmp_path / "dec.txt", DecodeOptions())  # progress 默认 None
    assert (tmp_path / "dec.txt").read_text(encoding="utf-8") == "hi"
```

- [ ] **步骤 2：运行测试验证失败** — `.venv/bin/pytest tests/test_progress.py -q`（新测试 FAIL：decode 不接受 progress）

- [ ] **步骤 3：修改 `qrtrans/decoder.py`**

顶部 import 增加：
```python
from typing import List, Optional
from .progress import ProgressCallback, ProgressEvent
```

`_gather_payloads` 增加可选 `progress` 参数并逐张发 `scan` 事件：

```python
def _gather_payloads(input_path: Path, progress: Optional[ProgressCallback] = None) -> List[Payload]:
    images = fs_walk.gather_images(input_path)
    total = len(images)
    payloads: List[Payload] = []
    for i, img_path in enumerate(images, start=1):
        with Image.open(img_path) as img:
            img.load()
            payloads.extend(qr_scan.scan(img))
        if progress is not None:
            progress(ProgressEvent("scan", i, total))
    return payloads
```

`decode` 函数：增加 `progress` 参数，传给 `_gather_payloads`；在重组循环里逐个发 `reassemble` 事件。把：

```python
def decode(input_path: Path, output: Path, options: DecodeOptions) -> DecodeResult:
    result = DecodeResult()
    payloads = _gather_payloads(input_path)
    ...
    reassembled: List[_FileReas] = []
    for fid, group in file_groups.items():
        reassembled.append(_reassemble_file(group))
```

改为：

```python
def decode(
    input_path: Path,
    output: Path,
    options: DecodeOptions,
    progress: Optional[ProgressCallback] = None,
) -> DecodeResult:
    result = DecodeResult()
    payloads = _gather_payloads(input_path, progress=progress)
    ...
    reassembled: List[_FileReas] = []
    total_files = len(file_groups)
    for i, (fid, group) in enumerate(file_groups.items(), start=1):
        reassembled.append(_reassemble_file(group))
        if progress is not None:
            progress(ProgressEvent("reassemble", i, total_files))
```

（其余 `decode` 逻辑——分组、strict、输出形态判定、rebuild——保持不变。）

- [ ] **步骤 4：运行测试验证通过** — `.venv/bin/pytest tests/test_progress.py -q`（8 passed）

- [ ] **步骤 5：回归** — `.venv/bin/pytest -q`（全绿）

- [ ] **步骤 6：Commit**

```bash
git add qrtrans/decoder.py tests/test_progress.py
git commit -m "feat(decoder): progress callback for scan and reassemble"
```

---

## 任务 4：CLI 默认进度 printer

**文件：** 修改 `qrtrans/cli.py`、`tests/test_cli.py`（追加）

- [ ] **步骤 1：追加失败的测试** — 在 `tests/test_cli.py` 末尾追加：

```python
def test_cli_encode_progress_to_stderr(tmp_path):
    # subprocess 捕获 stderr → 非 tty → 仅打阶段完成行；断言含进度字样
    src = tmp_path / "big.txt"
    src.write_text("X" * 4000)  # 多块，多帧
    out = tmp_path / "out"
    r = _run(["encode", str(src), "-o", str(out), "--batch", "cliprog1"])
    assert r.returncode == 0, r.stderr
    assert ("写帧" in r.stderr) or ("%" in r.stderr)
```

- [ ] **步骤 2：运行测试验证失败** — `.venv/bin/pytest tests/test_cli.py::test_cli_encode_progress_to_stderr -q`（FAIL：当前 encode 无进度输出到 stderr）

- [ ] **步骤 3：修改 `qrtrans/cli.py`**

在 `main` 之前增加默认 printer 工厂与标签映射：

```python
_PROGRESS_LABELS = {
    "prepare": "准备",
    "frame": "写帧",
    "qr": "生成",
    "scan": "扫描",
    "reassemble": "还原",
}


def _make_progress_printer():
    is_tty = sys.stderr.isatty()

    def _print(ev):
        label = _PROGRESS_LABELS.get(ev.phase, ev.phase)
        if ev.total > 0:
            pct = ev.current * 100 // ev.total
            line = f"{label} {ev.current}/{ev.total} ({pct}%)"
        else:
            line = label
        if is_tty:
            sys.stderr.write("\r" + line + "   ")
            sys.stderr.flush()
            if ev.current == ev.total:
                sys.stderr.write("\n")
        else:
            # 非 tty（重定向/CI 捕获）：仅阶段完成时打一行，避免 \r 污染日志
            if ev.current == ev.total:
                sys.stderr.write(line + "\n")

    return _print
```

在 `main` 的 encode 分支，把 `res = encode(args.input, args.outdir, opts)` 改为：

```python
            res = encode(args.input, args.outdir, opts,
                         progress=_make_progress_printer())
```

在 decode 分支，把 `res = decode(args.input, args.output, opts)` 改为：

```python
            res = decode(args.input, args.output, opts,
                         progress=_make_progress_printer())
```

- [ ] **步骤 4：运行测试验证通过** — `.venv/bin/pytest tests/test_cli.py -q`（含新测试，全绿）

- [ ] **步骤 5：Commit**

```bash
git add qrtrans/cli.py tests/test_cli.py
git commit -m "feat(cli): default single-line progress printer to stderr"
```

---

## 任务 5：全量回归 + 打包回归

- [ ] **步骤 1：全量测试** — `.venv/bin/pytest -q`（全部通过；预期 79 + 新增 ≈ 84+）

- [ ] **步骤 2：本地 frozen exe 冒烟（验证打包未被破坏）**

```bash
.venv/bin/pyinstaller packaging/qrtrans.spec --noconfirm >/dev/null 2>&1
./dist/qrtrans --help >/dev/null && echo "frozen --help OK"
printf 'QRTrans progress smoke 你好\n' > /tmp/opencode/in.txt
./dist/qrtrans encode /tmp/opencode/in.txt -o /tmp/opencode/qout --batch psmoke01 && echo "frozen encode OK"
rm -rf dist build
```
预期：frozen exe 仍可 build / --help / encode。

- [ ] **步骤 3：提交（如有 spec/文档微调）或留空**

> 无代码改动则跳过 commit；任务 1–4 已各自提交。

---

## 自检

### 1. 规格覆盖度
- §2 ProgressEvent/ProgressCallback：任务 1 ✓
- §3 encode 流式 array + prepare/frame/qr：任务 2 ✓
- §4 decode scan/reassemble：任务 3 ✓
- §5 CLI 默认 printer + isatty 回退：任务 4 ✓
- §6 测试（事件序列 + 向后兼容 + CLI stderr）：任务 1–4 ✓
- §7 影响面文件清单：与任务一致 ✓

### 2. 占位符扫描
- 每步含完整代码 ✓
- 无 TODO/"待定" ✓

### 3. 类型一致性
- `ProgressEvent(phase,current,total)` 全任务一致 ✓
- `encode(...,progress=None)`/`decode(...,progress=None)` 签名一致 ✓
- phase 字符串 `"prepare"|"frame"|"qr"|"scan"|"reassemble"` 在 encoder/decoder/cli 标签映射一致 ✓
- `paginate(payloads, spec.per_frame)` 与 array_pack.paginate 签名一致（泛型）✓

### 4. 范围
- 单一聚焦功能（进度 + 流式），4 个实现任务 + 1 个回归，可由一个计划覆盖 ✓
