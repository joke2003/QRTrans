# QRTrans 迁移到 Ubuntu Desktop — 待办清单

## 1. 环境准备

### 1.1 拷贝文件
- 将当前 `/home/kanshan/projects/QRTrans/` 整个目录拷贝到 Ubuntu Desktop（U盘/scp/共享文件夹均可）。
- 拷贝时**排除** `.venv/` 和 `.local-deps/`（平台相关，到 Ubuntu 重建）。

### 1.2 安装 Python 3.10+（Ubuntu 24.04 自带 3.12）
```bash
python3 --version   # 确认 ≥ 3.10
```
若版本过低：`sudo apt install python3.12 python3.12-venv`（见 sudotodo.md）。

### 1.3 创建虚拟环境 + 装依赖
```bash
cd <你拷贝到的目录>
python3 -m venv --without-pip .venv
curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
.venv/bin/python /tmp/get-pip.py
.venv/bin/python -m pip install -e ".[dev]"
```

### 1.4 验证安装
```bash
.venv/bin/pytest -q                          # 应 187 passed
.venv/bin/python -m qrtrans --help           # 应打印用法
.venv/bin/python -m qrtrans_viewer --help    # 应打印用法（需 python3-tk，见 sudotodo.md）
```

---

## 2. Viewer GUI 本地测试（核心目的）

### 2.1 验证 viewer 基本功能
```bash
# 生成几张测试帧
mkdir -p /tmp/cmtest
.venv/bin/python -m qrtrans encode /etc/hostname -o /tmp/cmtest --batch test0001

# 启动 viewer（全屏）
.venv/bin/python -m qrtrans_viewer /tmp/cmtest
```
验证：
- [ ] 真全屏（无边框、无标题栏）
- [ ] 首帧 3 秒分辨率提示出现并消失
- [ ] `→`/`Space` 下一张、`←` 上一张
- [ ] `P` 播放/暂停（角标 ▶/⏸ 切换）
- [ ] `+`/`-` 调间隔（角标数字变化）
- [ ] `O` 角标开关
- [ ] `Esc`/`Q` 退出
- [ ] `./qrtrans.json` 被写入（`cat qrtrans.json`）

### 2.2 验证 encoder 读 config 协同
```bash
# viewer 已写了 qrtrans.json，encoder 应自动读取
.venv/bin/python -m qrtrans encode /etc/hostname -o /tmp/cmtest2 --batch test0002
# 检查帧尺寸是否 = qrtrans.json 里的 screen 值
.venv/bin/python -c "from PIL import Image; print(Image.open(sorted(__import__('pathlib').Path('/tmp/cmtest2').glob('*.png'))[0]).size)"
```

### 2.3 端到端往返（Linux 全链路）
```bash
# encode（默认 colormatrix）→ viewer 显示 → 截屏 → decode
.venv/bin/python -m qrtrans encode ./docs -o /tmp/e2e_out --batch e2etest01
.venv/bin/python -m qrtrans decode /tmp/e2e_out -o /tmp/e2e_dec
diff -r ./docs /tmp/e2e_dec && echo "ROUNDTRIP OK"
```

---

## 3. PyInstaller 本地构建测试（可选）

### 3.1 构建 viewer frozen exe（Linux 版）
```bash
sudo apt install python3-tk           # 见 sudotodo.md
.venv/bin/python -m pip install pyinstaller
.venv/bin/pyinstaller packaging/qrtrans_viewer.spec --noconfirm
./dist/qrtrans-viewer /tmp/cmtest     # 应全屏显示
```

### 3.2 构建 main frozen exe（Linux 版）
```bash
sudo apt install libzbar0 binutils libpython3.12  # 见 sudotodo.md
.venv/bin/pyinstaller packaging/qrtrans.spec --noconfirm
./dist/qrtrans --help
./dist/qrtrans encode /etc/hostname -o /tmp/smoke --batch smoke001
./dist/qrtrans decode /tmp/smoke -o /tmp/smoke_dec
diff /etc/hostname /tmp/smoke_dec && echo "FROZEN ROUNDTRIP OK"
```

---

## 4. 日常开发（同此前流程）

- `.venv/bin/pytest -q` 跑全量测试。
- `.venv/bin/python -m qrtrans ...` 跑 CLI。
- `.venv/bin/python -m qrtrans_viewer ...` 跑 viewer（有显示器的优势）。
- Git 操作不变（`git push origin main` / `git tag v0.x.0`）。
- GitHub Actions 仍负责 Windows exe 构建（Linux 不能跨平台打 Windows exe）。

---

## 5. Win7 手测清单（下载 v0.3.0 exe 后）

- [ ] `qrtrans.exe --help` 退出 0
- [ ] `qrtrans.exe encode note.txt -o out\` → 产出 cm 帧
- [ ] `qrtrans.exe decode out\ -o dec.txt` → 内容一致
- [ ] 含中文/emoji 往返
- [ ] `qrtrans-viewer.exe out\` → 真全屏显示
- [ ] viewer 键盘（→/←/P/+/-/O/Esc）
- [ ] viewer 自动切换
- [ ] viewer 退出后 `qrtrans.json` 存在
- [ ] encoder 不传 `--screen` → 读 `qrtrans.json` → 帧尺寸匹配
- [ ] viewer 传不存在路径 → 弹窗报错、退出码 2（不崩）
