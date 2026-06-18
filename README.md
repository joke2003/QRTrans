# QRTrans

把文本文件/目录编码为多个二维码（含阵列打包，便于截屏传输），并能从二维码图像还原。

## 安装

```bash
# 系统依赖（pyzbar 需要）
sudo apt-get install -y libzbar0   # Debian/Ubuntu
pip install -e .
```

## 用法

```bash
# 编码（默认阵列模式，适配 1920x1080，每帧 3 个 QR）
qrtrans encode notes.txt -o qr_out/

# 编码整个目录（保留层级 + 空目录）
qrtrans encode ./mydir -o qr_out/

# 激进模式：每帧 10 个 QR（--grid WxH 列x行，5x2=5列2行；--module-px 2）
qrtrans encode big.txt -o qr_out/ --module-px 2 --grid 5x2 --no-label

# 自动布局
qrtrans encode big.txt -o qr_out/ --grid auto

# 单 QR 模式（每 QR 一张 PNG，适合打印）
qrtrans encode notes.txt -o qr_out/ --mode single

# 解码：输出形态由内容自动判定（单文件内容→写为单文件；目录内容→重建目录）
qrtrans decode qr_out/ -o decoded.txt      # 若编码内容是单个文件，写出 decoded.txt
qrtrans decode qr_out/ -o decoded_dir      # 若编码内容是目录，重建到 decoded_dir/
```

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
每个 QR 编码一段 JSON（方案 A 自描述分块）：含 `magic="QRT"`、批次 ID、相对路径、块序号 `ci/tc`、SHA-256、base64 数据。丢失任意 QR 只影响其所属文件。

详见 `docs/superpowers/specs/2026-06-17-qrtrans-design.md`。

## Windows 打包（单 exe）

通过 GitHub Actions 构建 Windows 单文件 `qrtrans.exe`，无需本地 Windows/Python。完整步骤（建仓库、认证、推送、触发、下载、验收、排错）见 [`docs/packaging-windows.md`](docs/packaging-windows.md)。

快速触发：推到 GitHub 后打 tag `git tag v0.1.0 && git push --tags`，工作流自动构建并在 Releases 发布 `qrtrans.exe`。
