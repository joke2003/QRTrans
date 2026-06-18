# QRTrans

把文本文件/目录编码为彩色矩阵帧（默认）/二维码阵列，便于截屏传输，并能从图像还原。

**默认模式 colormatrix**：全屏彩色矩阵，16 色 / 单元 4px，单帧约 50KB，密度约 4× QR 阵列。

## 安装

```bash
# 系统依赖（pyzbar 需要）
sudo apt-get install -y libzbar0   # Debian/Ubuntu
pip install -e .
```

## 用法

```bash
qrtrans encode notes.txt -o qr_out/                       # 默认 colormatrix
qrtrans encode ./mydir -o qr_out/                          # 目录（保留层级+空目录）
qrtrans encode big.txt -o qr_out/ --colors 32 --cell-px 3  # 更激进（密度更高）
qrtrans encode notes.txt -o qr_out/ --mode array           # 退回 QR 阵列（旧默认）
qrtrans encode notes.txt -o qr_out/ --mode single          # 单 QR（每 QR 一张 PNG，适合打印）
qrtrans decode qr_out/ -o decoded.txt                      # 自动检测 cm/QR
```

### 编码参数（colormatrix）

| 参数 | 说明 |
| --- | --- |
| `--mode colormatrix\|array\|single` | 默认 `colormatrix`（自 **v0.2.0** 起默认由 `array` 改为 `colormatrix`） |
| `--colors {4,8,16,32,64}` | 调色板色数，默认 16（色数越多密度越高，对屏幕色准要求越高） |
| `--cell-px` | 单元格像素，默认 4，最小 3 |
| `--cm-ecc` | Reed-Solomon 冗余百分比，默认 12（推荐 8–20） |
| `--compress / --no-compress` | 是否 zlib 压缩载荷（默认压缩；仅在确有收益时启用 `compressed=1`） |
| `--screen WxH` | 目标屏幕尺寸，默认 1920x1080（array 与 colormatrix 均使用） |

### 编码参数（QR 阵列 / single）

| 参数 | 说明 |
| --- | --- |
| `--mode array` | QR 阵列，默认 grid `4x2`（每帧 8 个 QR） |
| `--mode single` | 单 QR，每 QR 一张 PNG |
| `--module-px` | 每模块像素，默认 3 |
| `--grid WxH` | QR 阵列网格（列x行，如 `5x2`）或 `auto`；仅 array |
| `--ec L\|M\|Q\|H` | QR 纠错级别，默认 M |
| `--label / --no-label` | 阵列图顶是否加帧标签横幅（默认加） |

> **兼容性提醒**：旧脚本若依赖默认 QR 阵列，请显式加 `--mode array`。

## 退出码
- `0` 成功
- `1` 部分成功（默认模式下有缺失/损坏，其余已恢复）
- `2` 失败

## 进度反馈
encode/decode 默认在 **stderr** 输出进度（不污染 stdout 的机器可读输出）：
- 交互终端（cmd/PowerShell 等）：单行刷新，如 `写帧 3/10 (30%)`、`扫描 5/8 (62%)`。
- 重定向到文件（非 tty）：仅在每个阶段完成时打一行，避免 `\r` 污染日志。

库用法：`encode(..., progress=cb)` / `decode(..., progress=cb)`，`cb` 收到 `ProgressEvent(phase, current, total)`；不传则静默。

## 协议
- **QR 阵列 / single**：每个 QR 编码一段 JSON（方案 A 自描述分块）：含 `magic="QRT"`、批次 ID、相对路径、块序号 `ci/tc`、SHA-256、base64 数据。丢失任意 QR 只影响其所属文件。
- **colormatrix**：独立二进制帧格式（自描述头 + RS 编码载荷 + 四角 finder 标记），不使用 JSON。

`qrtrans decode` 自动检测帧类型并在两种格式间分流。详见 `docs/superpowers/specs/2026-06-17-qrtrans-design.md`。

## Windows 打包（单 exe）

通过 GitHub Actions 构建 Windows 单文件 `qrtrans.exe`，无需本地 Windows/Python。完整步骤（建仓库、认证、推送、触发、下载、验收、排错）见 [`docs/packaging-windows.md`](docs/packaging-windows.md)。

快速触发：推到 GitHub 后打 tag `git tag v0.1.0 && git push --tags`，工作流自动构建并在 Releases 发布 `qrtrans.exe`。
