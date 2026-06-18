# QRTrans 彩色矩阵（colormatrix）模式 设计规格

- **日期**：2026-06-18
- **状态**：待审查
- **关联**：`docs/superpowers/specs/2026-06-17-qrtrans-design.md`（主程序）；`docs/superpowers/notes/2026-06-18-colormatrix-kickoff-prep.md`（验证与决策笔记）

---

## 1. 目标与非目标

### 目标
新增一个**高密度视觉传输模式 `colormatrix`**：用全屏**彩色单元格矩阵**替代 QR 阵列作为默认编码方式，在 1920×1080 截屏信道下把单帧有效载荷从 QR 的 ~13–39KB 提升到 **~50–95KB**（约 4–7×）。模式与现有 QR（`array`/`single`）**共存**，QR 改为手动指定。

### 非目标（YAGNI）
- 不替换/废弃 QR 模式（向后兼容）。
- 不支持摄像头/拍照信道（仍假定无损 PNG 截屏；JPEG 是已知风险，靠强制 PNG 规避）。
- 不做动画/视频传输（独立未来方向）。
- 不做调色板的运行时自由编辑（仅固定档位 K∈{4,8,16,32,64}）。

---

## 2. 模式与 CLI

### `--mode` 取值
- `colormatrix`（**新默认**）
- `array`（QR 阵列，原默认）
- `single`（QR 单张）

### colormatrix 新增参数
| 参数 | 默认 | 说明 |
|---|---|---|
| `--colors` | `16` | 调色板档位：4/8/16/32/64（数值越大密度越高、越脆；默认 16=稳健甜点） |
| `--cell-px` | `4` | 单元格像素边长；3=激进（密度高），4=稳健，2 不支持（缩放太脆） |
| `--cm-ecc` | `12` | Reed-Solomon 冗余百分比（0–30） |
| `--no-compress` | 关 | 关闭自动 zlib 压缩（默认开，有收益才用） |

复用既有：`--screen WxH`（默认 1920x1080，决定网格规模）、`--batch`、`--label/--no-label`（帧标签横幅，人类辅助）、进度回调。

### QR 模式默认值调整
- `--grid` 默认由 `3x1` **改为 `4x2`**（module_px 仍为 3）。**注意**：4x2 在 3px 下几何上略超 1920×1080，靠显示端轻微缩放下仍可扫（用户实测单色可接受）；用户可手调 `--grid`/`--module-px`。本改动**仅影响默认值**，几何判定与 `auto_grid` 逻辑不变。

### 兼容性
- 既有 `--mode single|array` 行为零变化；所有既有测试（指定 mode 的）不受影响。
- 默认翻转：脚本若依赖旧默认（不指定 `--mode`）将从 QR 阵列变为 colormatrix——在 README 与发布说明里明示。

---

## 3. 调色板（`qrtrans/palette.py`）

- 固定档位 **K∈{4,8,16,32,64}**；`build_palette(K)` 返回 K 个 sRGB 颜色（贪心最远点，**确定性、版本固定**，视作格式的一部分，永不改动）。
- `nearest(palette, rgb)`：返回最近色索引（欧氏距离）。
- 帧头带 `palette_version` 字节（当前=1），未来若换调色板可升版本。

> 实验依据：16 色/4px 在所有测试场景（含 JPEG、缩放、gamma、色偏）0% 误判；32/64 色在无损下 0%、但 JPEG 下脆。故默认 16/4。

---

## 4. 帧结构（colormatrix 单帧 = 一张全屏 PNG）

一帧由三部分组成（均为单元格，统一渲染）：

1. **finder 标记（四角）**：每个角放一个固定图形——一个"标记色"实心方块（标记色为调色板之外的保留色，如纯黑）外加白色环，边长约 `2×cell_px`。解码端据此**定位 + 仿射修正**（处理 viewer 的轻微缩放/裁剪/倾斜）。
2. **帧头区（顶部保留若干单元格行）**：用单元格编码的二进制元信息，字段：
   - `magic`(4B，如 `CMTX`)、`version`(1B)、`palette_version`(1B)、`K`(1B)、`cell_px`(1B)、`grid W×H`(各 2B)、`batch`(8 位 hex)、`frame_index`(2B)、`frame_total`(2B)、`cm_ecc_percent`(1B)、`compressed`(1B)、`payload_total_bytes`(4B)、`payload_sha256`(32B)、`header_crc32`(4B)
   - 帧头**单独 RS 保护**（或重复 3 份多数表决），因帧头损坏则整帧不可解析。编码方式：字节→拆成 4-bit 半字节→映射到 K≥16 的色索引（每半字节 1 单元格）；对 K<16 用 2 单元格/字节。
3. **载荷区（其余单元格）**：每单元格一个调色板索引 = 数据流的可视化。

> 精确字节布局、单元格行数在实现计划里定；本规格只约束字段集合与上述策略。

---

## 5. 纠错策略（Reed-Solomon，批量级 + 擦除纠正）

- 用 `reedsolo` 库对**整批 payload**（压缩后）做一次 RS（默认 12%，可 `--cm-ecc` 调），再分帧。
- 解码端按 `frame_index` 把**缺失的帧当作擦除（erasure）**——RS 擦除纠正能力是错误纠正的 2 倍：12% 冗余可容忍约 **24% 帧丢失**仍完整还原。
- 这与 QR 模式"每块独立、丢块=该文件不完整"不同：colormatrix 在冗余范围内可**从丢帧中恢复**。
- **约束**：解码需至少 `(1−ecc_rate)` 比例的帧到场；不足则失败（`--strict` 与尽力恢复语义沿用：能 RS 还原即还原，不能则报错/告警）。

---

## 6. 压缩（zlib，自动）

- 编码端：对 payload 跑 zlib；若 `len(compressed) < len(raw)` 则用压缩版并置 `compressed=1`，否则置 0。`--no-compress` 强制关闭。
- 解码端按 `compressed` 标志解压。
- 收益：可压缩内容（文本、office 文档 XML）再 ×2–5；已压缩内容（jpg/zip/docx 内部）几乎无收益但无害（自动选不压）。

---

## 7. 编码管线（`colormatrix_encode`）

```
input(file|dir)
  └─[fs_walk]→ Records                                    # 复用
      └─[chunker 概念]→ 批 payload bytes（含自描述元数据）
          └─[zlib(可选)]→ bytes'
              └─[reedsolo RS]→ bytes''                     # 批级 ECC
                  └─ 分帧（每帧 payload 区容量 = W×H − finder − header）
                      └─ 逐帧：填帧头 + finder + 载荷单元格
                          └─[PIL NEAREST 渲染全屏 PNG]
        progress: prepare / frame i/N
```

每帧的载荷容量 = `(W×H 单元数) − (finder 占用) − (header 单元数)`，其中 W=floor(screen_w/cell_px)、H=floor((screen_h−banner)/cell_px)。

---

## 8. 解码管线（`colormatrix_decode`，自动检测）

```
input(file|dir of PNG)
  └─ 对每张图：检测 finder 标记
       ├─ 命中 finder → colormatrix 帧
       │    └─ 定位 4 标记 → 仿射变换归一 → 采样单元中心 → nearest 调色板 → 索引
       │        └─ 拼出帧头 + 载荷 → 按 frame_index 收集
       └─ 未命中 → 该图走 QR 路径（pyzbar）
  └─ 按 magic 分流：colormatrix 帧聚合 / QR 载荷聚合
       ├─ colormatrix：RS 纠错（缺失帧=擦除）→ 解压 → 校验 sha256 → 还原 Records → rebuild
       └─ QR：沿用既有 decoder
```

- 解码端**自动检测**帧类型，故输入目录可混合（虽然单批应一致）。
- 几何修正：4 个 finder 角点求仿射矩阵，把捕获图映射回标准网格；对每单元格中心采样（中心点远离边缘抗锯齐）。

---

## 9. 模块结构

| 文件 | 职责 |
|---|---|
| `qrtrans/palette.py` | 固定调色板（K∈{4,8,16,32,64}）、`nearest` |
| `qrtrans/cm_protocol.py` | 帧二进制格式：帧头编/解码、magic、字节↔色索引映射、CRC |
| `qrtrans/finder.py` | finder 标记渲染（encode 侧）+ 定位与仿射（decode 侧） |
| `qrtrans/cm_encoder.py` | colormatrix_encode：压缩→RS→分帧→渲染，含进度 |
| `qrtrans/cm_decoder.py` | colormatrix_decode：检测→几何→采样→RS→解压→还原，含进度 |
| `qrtrans/dispatch.py`（或并入 cli） | encode/decode 入口按 mode/检测结果分流到 QR 或 colormatrix |
| 修改 `qrtrans/cli.py` | 新 mode、新参数、默认翻转、分流调用、进度 |
| 修改 `qrtrans/decoder.py` / `encoder.py` | 仅作被分流方（QR 路径保持不变） |

复用：`fs_walk`、`chunker`（payload 拼装概念）、`progress`、`protocol`（QR 载荷不变）。

---

## 10. 依赖与打包

- 新增 `reedsolo>=1.7`（纯 Python，PyPI）→ `pyproject.toml`。
- PyInstaller spec：`collect_dynamic_libs` / `collect_submodules` 加 `reedsolo`；`hiddenimports` 加 `reedsolo`、新 `qrtrans.cm_*` / `palette` / `finder`。
- Windows exe（Python 3.8，Win7 兼容）：实现完成后重出 release（`v0.2.0`）。

---

## 11. 测试策略

- **palette**：确定性（同 K 同结果）、`nearest` 正确性、各 K 档位合法。
- **cm_protocol**：帧头往返、CRC 检测损坏、字节↔色索引边界。
- **finder**：合成图上定位 4 角、轻微缩放/平移下仿射修正正确。
- **端到端往返**（核心）：
  - 小文本、长文本（多帧）、中文/emoji、嵌套目录+空目录、二进制（含 NUL/高位字节，证明非文本也能走）。
  - 默认参数（16色/4px）往返一致。
  - `--colors 32`、`--cell-px 3`、`--no-compress`、`--cm-ecc 20` 各可调且往返一致。
  - **丢帧可恢复**：删 1 帧在 RS 范围内仍完整还原；删超量帧失败/告警。
  - **压缩自动**：文本触发压缩、随机字节不压缩（标志位正确）。
- **解码自动检测**：QR 目录与 colormatrix 目录分别正确分流；混合目录正确。
- **CLI**：默认 mode=colormatrix、`--colors`/`--cell-px` 生效、QR 用 `--mode array` 仍可。
- **回归**：既有 89 测试全绿；QR `--grid` 新默认 4x2 加一条用例。

---

## 12. 风险与应对

| 风险 | 应对 |
|---|---|
| viewer 轻微缩放致几何偏移 | finder 标记 + 仿射修正 + 单元中心采样（QR/pyzbar 已证 finder 定位在该信道可行） |
| 跨机色偏 | 已实测 0% 影响（高 ΔE 调色板 + 最近色匹配）；帧头 `palette_version` 兜底 |
| JPEG 重压缩 | 强制 PNG（默认就是）；文档与排错说明 |
| 帧头损坏 | 帧头独立 RS / 多数表决 |
| 默认模式翻转影响老脚本 | README + 发布说明明示；`--mode array` 显式回退 |
| 复杂度（新 codec） | 模块化、TDD、子代理驱动 + 两阶段审查 |

---

## 13. 未来扩展（不在本次范围）
- 动画/视频传输（时间维度 ×）。
- 自定义/更大调色板（K>64，需亮度校准）。
- 跨 QR/colormatrix 混合批次的统一索引。
- 彩色矩阵的 `auto` cell-px/colors 自适应（按屏幕与可靠性）。
