# QRTrans 设计规格

- **日期**：2026-06-17
- **状态**：待审查
- **作者**：设计草案（brainstorming 产出）

---

## 1. 目标与非目标

### 目标
提供一个 Python 命令行工具 `qrtrans`，支持：

1. **编码（encode）**：将一个文本文件，或一个含层级子目录的文本文件集合，拆分并编码为多个二维码（QR Code）图像。
2. **解码（decode）**：从一张或一个目录下的二维码图像（含二维码阵列）中还原出原始文本文件或目录结构。
3. **阵列打包（array mode）**：把多个二维码拼成一张适配屏幕（默认 1920×1080）的网格 PNG，便于通过截屏一次性传输多张二维码，减少截屏次数。

### 非目标（YAGNI）
- 不做摄像头实时扫描。
- 不内置全屏显示窗口（只输出 PNG，由用户用看图器打开后截屏）。
- 不支持二进制文件（图片、PDF 等）；仅处理文本（UTF-8）。
- 不做加密（如需保密，用户应在外层自行加密后再喂给本工具）。
- 不做网络传输。

---

## 2. 使用场景与核心约束

- **主场景**：气隙（air-gapped）/ 一次性传输。环境可控，QR 来源为直接截屏（无倾斜、无光照问题，是解码的最理想情况）。
- **运行环境**：Python 3.9+。
- **解码依赖**：系统需安装 `libzbar0`（pyzbar 的运行时依赖）。

---

## 3. 顶层架构

采用模块化、单一职责的设计。每个模块可独立理解和测试，通过明确接口通信。

```
qrtrans/
  __main__.py        # 入口：python -m qrtrans / console_script qrtrans
  cli.py             # argparse 解析、子命令分发
  config.py          # 默认值、选项 dataclass（EncodeOptions / DecodeOptions）
  protocol.py        # 载荷 JSON schema：dict <-> Payload dataclass，版本/魔数校验
  chunker.py         # 原始字节流 <-> 数据块（带 ci/tc/sha256 元信息）
  fs_walk.py         # 输入：遍历 文件/目录 -> Record 列表；输出：Record 列表 -> 目录树重建
  qr_render.py       # Payload -> 单张 QR 的 PIL.Image（含静默区）
  qr_scan.py         # PIL.Image -> [Payload]（pyzbar 封装）
  array_pack.py      # [PIL.Image] + 帧元信息 -> 阵列 PNG（含可选标签横幅）
  encoder.py         # 高层 encode 流程：Record 列表 -> Payload 列表 -> QR 图像 -> 阵列/单张输出
  decoder.py         # 高层 decode 流程：图像 -> Payload 列表 -> 文件重建
```

### 模块职责一句话

| 模块 | 职责 |
|---|---|
| `cli` | 解析参数、构造 Options、调用 encoder/decoder |
| `protocol` | 定义并校验单 QR 载荷格式（详见 §5） |
| `chunker` | 切分/拼接数据块，维护 `ci/tc/sha256` |
| `fs_walk` | 文件系统↔Record 抽象，处理路径、空目录 |
| `qr_render` | 单 QR 渲染（含静默区） |
| `qr_scan` | 单张图像→Payload 列表（pyzbar 自动返回图中所有 QR） |
| `array_pack` | 多 QR→单张阵列 PNG（含标签横幅） |
| `encoder` / `decoder` | 串联以上模块完成端到端流程 |

---

## 4. CLI 接口

```
qrtrans encode <input> -o <outdir> [options]
qrtrans decode <input> -o <output> [options]
```

### encode

| 参数 | 默认 | 说明 |
|---|---|---|
| `<input>` | 必填 | 单个文本文件或目录 |
| `-o, --outdir` | 必填 | 输出目录（自动创建） |
| `--mode` | `array` | `single`（一 QR 一文件）或 `array`（多 QR 一帧） |
| `--screen` | `1920x1080` | 目标屏幕 `WxH`，用于 array 布局计算 |
| `--module-px` | `3` | 每模块像素数；增大更易扫，减小更密集 |
| `--grid` | `3x1` | array 网格 `WxH`（列×行，如 `3x1`=3 列 1 行）；`auto` 表示按 `--screen`/`--module-px` 自动算最密布局 |
| `--ec` | `M` | QR 纠错等级 `L/M/Q/H` |
| `--chunk-raw-bytes` | `1300` | 每块原始字节上限（base64 后约 1734 字符） |
| `--label / --no-label` | `--label` | 是否在阵列图顶添加人类可读的帧标签横幅 |
| `--batch` | 自动生成 | 批次 ID（8 位十六进制）；不指定则随机 |

### decode

| 参数 | 默认 | 说明 |
|---|---|---|
| `<input>` | 必填 | 单张图像文件，或一个含图像的目录 |
| `-o, --output` | 必填 | 输出文件（单源文件时）或输出目录（多文件时） |
| `--strict` | 关 | 开启后任一块缺失/校验失败即整体失败并退出码非 0；默认尽力恢复并打印告警 |

### 退出码
- `0` 成功
- `1` 部分成功（非 strict 下有缺失/损坏）
- `2` 失败（输入错误、strict 下任一失败、致命错误）

---

## 5. 载荷协议（核心）

每个 QR 编码一段 UTF-8 JSON。**方案 A：自描述分块**——每块携带完整归属信息，互不依赖。

### 5.1 JSON Schema

```json
{
  "magic": "QRT",          // 固定，格式标识
  "ver": 1,                // 协议版本（整数），当前为 1
  "batch": "a1b2c3d4",     // 批次 ID（8 位十六进制），同一次 encode 共享
  "type": "file",          // "file" | "dir"
  "fid": "f01",            // 该文件在本批次的稳定短 ID
  "fn": "notes.txt",       // 原始文件名（basename）
  "path": "docs/notes.txt",// 相对批次根的路径（保留目录层级；正斜杠分隔）
  "ci": 0,                 // 数据块索引（0-based）
  "tc": 3,                 // 该文件的块总数
  "enc": "b64",            // data 字段编码，固定 "b64"
  "sha256": "<hex>",       // 原始文件字节的 SHA-256（type=file 时所有块均带，便于任一存活块校验）
  "data": "<base64>"       // type=file：base64(UTF-8 文本片段)；type=dir：空字符串
}
```

### 5.2 关键规则

- **魔数与版本**：解码时必须校验 `magic == "QRT"`；`ver` 高于支持版本则报错。
- **type=file**：`tc ≥ 1`，`data` 为块内容。`ci ∈ [0, tc)`。
- **type=dir（空目录标记）**：`tc=1, ci=0, data="", sha256=""`。`path` 以 `/` 结尾。用于保留空目录。
- **路径分隔**：`path` 始终用正斜杠 `/`，`fn` 为 basename。解码端用 `os.sep` 重建本地路径。
- **路径安全**：解码端重建前必须校验 `path` 不含 `..`、不是绝对路径，防止路径穿越。
- **批次 ID**：用于区分混在同一目录下的多次 encode 产物；解码端按 `fid` 聚合（同 fid 必有同 batch）。

### 5.3 为什么 base64 而非裸 UTF-8
JSON 字符串字段需为合法 Unicode；base64 保证任意字节可安全嵌入，且便于 JSON 解析与人工调试。代价约 +33% 体积，在气隙一次性场景可接受。

### 5.4 容量与分块（QR Version 40 / EC-M）
QR Version 40 在字节模式下、EC-M（15% 纠错）容量 = **2331 字节**。

- JSON 元数据开销 ≈ 250 字节（路径、ID、sha256 等）。
- 留约 350 字节安全余量 → 每块 JSON 总长 ≤ ~1980 字节。
- base64 膨胀 4/3 → 每块**原始字节上限 = 1300**（默认）→ base64 ≈ 1734 字符。
- 配置项 `--chunk-raw-bytes` 允许下调（更稳）或上调（不可超过使 JSON 超 2200 字节，实现需做断言）。

---

## 6. 阵列打包（array mode）

### 6.1 静默区与布局模型
- 单 QR = Version 40 = 177×177 模块。
- 渲染时每个 QR 自带 4 模块 border（即 qrcode 库的 quiet zone）。因此单 QR 图像边长 = `177 + 8 = 185` 模块 = `185 × module_px` 像素，记为 `cell_px`。
- 阵列按 R×C 网格**边贴边**排列（相邻 QR 各自的 4 模块 border 叠加为 8 模块间隔，超过标准的 4 模块最小值，扫描更宽松；实现上更简单且每个 QR 抽出后仍可单独扫描）。
- 像素尺寸：阵列宽 = `C × cell_px`，高 = `R × cell_px + (40 if label else 0)`。

### 6.2 1920×1080 下的可行布局（V40、border=4、含 40px 横幅）

`cell_px = 185 × module_px`

| `--module-px` | `--grid` | 帧像素（宽×高） | QR/帧 | 可扫性 |
|---|---|---|---|---|
| **3（默认）** | **3x1（默认）** | **1665×595** | **3** | **稳，截屏首选** |
| 3 | 2x1 | 1110×595 | 2 | 最稳 |
| 2 | 5x2 | 1850×780 | 10 | 密度最高，2px 模块在干净截屏下可扫但略冒险 |
| 4 | 2x1 | 1480×780 | 2 | 最稳，模块大 |

注：2×2 at 3px = 1110×1110，加横幅 1150，**超出 1080**，不可用；要 2×2 必须 V30 或更小模块。

### 6.3 默认值
- `--module-px 3`、`--grid 3x1` → `cell_px=555`，每帧 **3 个 QR**，帧尺寸 **1665×595 像素**，1920×1080 屏幕下两侧各留约 128px、下方留约 485px 余量，适配截屏。

### 6.4 自动布局（`--grid auto`）
给定 `--screen WxH`、`--module-px p`、横幅高 `B=40`、`cell_px = 185p`：
- 最大列数 `C_max = floor(W / cell_px)`
- 最大行数 `R_max = floor((H - B) / cell_px)`
- 取 `C_max × R_max`。

验算 1920×1080、p=3：`cell_px=555`，`C_max = floor(1920/555) = 3`，`R_max = floor(1040/555) = 1` → **3×1**，与默认一致。
p=2：`cell_px=370`，`C_max = 5, R_max = 2` → **5×2 = 10 QR/帧**（激进模式）。

### 6.5 帧标签横幅（默认开启）
- 图顶一条高 40 像素的横幅，文字：`batch=<id> frame <i>/<N>`。
- 纯人类辅助，**不进入 QR 内容**；用 `--no-label` 关闭（关闭后布局高度减 40px，可容纳略多行）。

### 6.6 文件命名
- `single` 模式：`qrtrans_<batch>_<NNNN>.png`（4 位顺序号，跨整个批次）。
- `array` 模式：`qrtrans_<batch>_frame_<NN>.png`（2 位帧号）。

### 6.7 分页规则
- 按 `--grid` 容量（默认 3 QR/帧）顺序填入所有 QR。
- 末帧不足 N 个时，仍按实际数量渲染（剩余位置留白）。

---

## 7. 解码流程

### 7.1 输入识别
- `<input>` 是文件：当作单张图像解码。
- `<input>` 是目录：递归 glob 所有 `*.png/*.jpg/*.jpeg`，逐张解码。
- pyzbar 自动返回每张图像中的**所有** QR，因此单张和阵列都无需区分。

### 7.2 重组算法
1. 扫描所有图像 → 收集所有 Payload。
2. 校验 `magic`/`ver`；丢弃非本格式 QR。
3. 按 `fid` 分组；同 `fid` 必须共享同一 `batch`。
4. 对每个 `fid`：
   - `type=dir`：在输出根下创建空目录（按 `path`）。
   - `type=file`：检查 `ci ∈ [0, tc)` 是否齐全。
     - 齐全且 base64 解码、按 `ci` 拼接 → 计算 SHA-256 与 `sha256` 比对。
     - 一致 → 按 `path` 写入。
     - 不一致或缺失块：
       - `--strict`：失败并退出码 2。
       - 默认：跳过该文件，记录到告警列表，继续处理其他文件。
5. 输出告警摘要：缺失块列表、校验失败文件、未识别图像。

### 7.3 输出形态判定（无歧义规则）
**由解码出的载荷结构决定，既不依赖 `-o` 末尾字符，也不依赖输入是文件还是目录**（因为 array 编码产物总是目录，"输入是目录"无法区分单文件内容与目录内容）。

| 可恢复文件数（ok） | 目录标记数（type=dir） | 行为 |
|---|---|---|
| 1 | 0 | `-o` 视为**文件路径**，直接写入（即使输入是含 PNG 的目录） |
| 0 | 1 | `-o` 视为**目录**，创建空目录 |
| 任意 | 或 多文件 / 含目录标记 | `-o` 视为**目录**，按 `path` 重建层级 |

> 边角：编码内容恰好为"含 1 个文件、无空子目录"的目录时，解码会按单文件写出（`-o` 作为文件）。这是为避免主用例（单文件 array 编码→单文件解码）崩溃的合理取舍；如需强制目录输出，可在编码时加入一个空子目录。

> 全部文件重组失败且无目录标记时，不创建误导性的空输出目录（仅在至少有 1 个可写文件或目录标记时才 `rebuild`）。

---

## 8. 错误处理与恢复语义

| 情况 | 默认行为 | `--strict` 行为 |
|---|---|---|
| 某文件缺失若干块 | 跳过该文件，告警，继续 | 失败，退出码 2 |
| SHA-256 不匹配 | 跳过该文件，告警 | 失败，退出码 2 |
| 输入目录含无关图像 | 忽略，告警 | 同 |
| JSON 解析失败 / magic 错误 | 忽略该 QR，告警 | 同 |
| 路径穿越攻击（`..`/绝对路径） | 拒绝该条目，告警 | 失败，退出码 2 |
| 输入不存在 / 不可读 | 失败，退出码 2 | 同 |

恢复原则：**自描述协议保证丢失任意 QR 只影响其所属文件，其他文件不受影响**。

---

## 9. 依赖

| 包 | 用途 | 来源 |
|---|---|---|
| `qrcode` | QR 生成 | PyPI |
| `Pillow` | 图像操作（QR 像素化、阵列拼接、标签横幅） | PyPI |
| `pyzbar` | QR 解码（需系统 `libzbar0`） | PyPI |
| 标准库 | `argparse/json/base64/hashlib/pathlib/dataclasses/typing/secrets` | 内置 |

打包建议：`pyproject.toml` + `console_scripts` 入口 `qrtrans = qrtrans.cli:main`。

---

## 10. 测试策略（TDD）

使用 `pytest`。核心测试矩阵：

- **协议层**：Payload 往返、版本校验、坏 magic 拒绝、路径穿越拒绝。
- **分块层**：切分后块数正确；拼接还原等价；边界（空文件、恰好整除、非整除）。
- **fs_walk**：单文件、嵌套目录、空目录、Unicode 文件名。
- **端到端往返**（最重要）：
  - 短文本（1 块）
  - 长文本（多块，>1300 字节）
  - 含中文/emoji 的 UTF-8
  - 多文件嵌套目录 + 空目录
  - `single` 与 `array` 两种模式均往返一致
- **阵列解码**：array 帧图像 → pyzbar 检出该帧全部 QR → 重组成功。
- **恢复语义**：人为删除某 QR 图像后 decode，验证其余文件仍恢复、告警正确；`--strict` 下退出码正确。
- **完整性**：SHA-256 校验通过；篡改某块后校验失败被检出。

测试不依赖外部系统（除 pyzbar 需 `libzbar0`，CI 中通过 apt 安装）。

---

## 11. 模块间数据流

### encode
```
input(file|dir)
  └─[fs_walk]→ Records [(path, bytes)]
      └─[chunker]→ per-file Chunks [(ci, tc, sha256, payload_bytes)]
          └─[protocol]→ Payloads (dict)
              └─[qr_render]→ QR Images [PIL.Image]
                  └─[array_pack]→ Frame PNGs   (array mode)
                   或 直接写出                  (single mode)
```

### decode
```
input(file|dir of images)
  └─[qr_scan]→ Payloads
      └─[protocol 校验]→ 有效 Payloads
          └─ 按 fid 分组 → [chunker 拼接 + sha256 校验] → Records
              └─[fs_walk 重建]→ 输出文件/目录
```

---

## 12. 未来扩展（不在本次范围）
- 二进制文件支持（schema 已用 base64，只需放开输入类型）。
- 实时全屏显示模式（GUI）。
- Reed-Solomon 跨块冗余（前向纠错，容忍整块丢失）。
- 加密层。
- 多批次索引合并。
