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

# 激进模式：每帧 10 个 QR（5x2，2px 模块）
qrtrans encode big.txt -o qr_out/ --module-px 2 --grid 5x2 --no-label

# 自动布局
qrtrans encode big.txt -o qr_out/ --grid auto

# 单 QR 模式（每 QR 一张 PNG，适合打印）
qrtrans encode notes.txt -o qr_out/ --mode single

# 解码（单张或多文件目录）
qrtrans decode qr_out/ -o decoded.txt      # 单文件
qrtrans decode qr_out/ -o decoded_dir/     # 目录
```

## 退出码
- `0` 成功
- `1` 部分成功（默认模式下有缺失/损坏，其余已恢复）
- `2` 失败

## 协议
每个 QR 编码一段 JSON（方案 A 自描述分块）：含 `magic="QRT"`、批次 ID、相对路径、块序号 `ci/tc`、SHA-256、base64 数据。丢失任意 QR 只影响其所属文件。

详见 `docs/superpowers/specs/2026-06-17-qrtrans-design.md`。
