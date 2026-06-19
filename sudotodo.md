# 迁移到 Ubuntu Desktop — 需要 sudo 安装的系统包

> 在 Ubuntu Desktop 终端逐条执行。每条附说明，按需安装。

## 必装（viewer GUI 测试 + 开发）

### python3-tk（Tkinter，viewer GUI 必需）
```bash
sudo apt install python3-tk
```
- **为什么**：viewer 用 Tkinter 全屏 GUI；无此包 `import tkinter` 会 `ModuleNotFoundError`。
- **验证**：`python3 -c "import tkinter; print('tk ok')"`

## 必装（PyInstaller frozen 构建）

### binutils（PyInstaller 解析二进制依赖）
```bash
sudo apt install binutils
```
- **为什么**：PyInstaller 用 `objdump`（来自 binutils）分析 .so 依赖；缺则构建报错。

### libpython3.12（Python 共享库，PyInstaller 需要）
```bash
sudo apt install libpython3.12
```
- **为什么**：PyInstaller 把 Python 解释器打进 exe，需要 `libpython3.X.so.1.0`；系统 Python 默认不带。
- **验证**：`ldconfig -p | grep libpython`

### libzbar0（QR 解码，pyzbar 运行时依赖）
```bash
sudo apt install libzbar0
```
- **为什么**：pyzbar 通过 ctypes 加载 `libzbar.so.0`；无此库 QR 解码 `ImportError`。
- **注意**：如果之前在 headless 服务器上手动解压过 `.local-deps/` 的 .deb，在 Ubuntu Desktop 上直接用 apt 装更干净（`.local-deps/` 是 headless 无 sudo 时的 workaround，可以不用了）。
- **验证**：`python3 -c "from pyzbar.pyzbar import decode; print('zbar ok')"`

## 可选（GitHub CLI，用于触发 CI / 下载 release）

### gh（GitHub CLI）
```bash
sudo apt install gh
gh auth login   # 浏览器授权
```
- **为什么**：触发 GHA 构建、下载 release exe、管理 repo。
- **如果 apt 里 gh 版本旧**：访问 https://cli.github.com 装最新。

## 一键全装（复制粘贴）

```bash
sudo apt update && sudo apt install -y python3-tk binutils libpython3.12 libzbar0 gh
```

## 装完验证

```bash
python3 -c "import tkinter; print('tk ok')"
python3 -c "from pyzbar.pyzbar import decode; print('zbar ok')"
which objdump && objdump --version | head -1
ldconfig -p | grep libpython
gh --version
```
全部通过即可开始 `todo.md` 里的步骤。
