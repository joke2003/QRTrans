# QRTrans Windows 单 exe 打包设计规格

- **日期**：2026-06-18
- **状态**：待审查
- **关联**：`docs/superpowers/specs/2026-06-17-qrtrans-design.md`（主程序设计）

---

## 1. 目标与非目标

### 目标
将 QRTrans 打包成**单个 Windows x64 可执行文件** `qrtrans.exe`，无需目标机安装 Python 或任何依赖即可运行 encode/decode。构建在 **GitHub Actions** 的 `windows-latest` 托管运行器上进行，产物作为 CI Artifact / Release 提供，用户下载即用。

### 非目标（YAGNI）
- 不做代码签名（需付费证书，杀软误报用户已确认可接受）。
- 不做 32 位（x86）构建。
- 不做自动更新。
- 不在本地 Linux 交叉编译（PyInstaller 不支持跨平台）。
- 不做本地 Windows 构建脚本（已统一到 CI）。

---

## 2. 总体方案

| 维度 | 方案 |
|---|---|
| 构建环境 | GitHub Actions `windows-latest` 托管运行器 |
| 打包工具 | PyInstaller（`--onefile --console`，x64） |
| libzbar 处理 | 见 §3（关键，已验证可大幅简化） |
| 仓库 | Public（公共仓库 Actions 免费额度无限） |
| 触发 | 手动 `workflow_dispatch` + 打 `v*` tag 自动构建并发布 Release |
| 产物分发 | Actions→Artifacts（每次运行）；Releases 页面（tag 触发） |
| 入口 | `qrtrans/__main__.py`（已存在的 `python -m qrtrans` 入口） |

---

## 3. libzbar 在 Windows 的处理（核心，已实证）

**关键发现（已验证）**：`pyzbar` 的 Windows 官方 wheel `pyzbar-0.1.9-py2.py3-none-win_amd64.whl` **已内置** `libzbar-64.dll`（167KB）与 `libiconv.dll`（981KB）于 `pyzbar/` 包目录内。已解压核实。

由此：
- 在 Windows 上 `pip install pyzbar` 自动得到这两个 DLL，无需任何外部下载。
- pyzbar 的 Windows 加载器在 `Path(__file__).parent`（即包目录）查找 `libzbar-64.dll`，天然匹配。
- **CI 工作流无需写任何 DLL 下载步骤**；也无需固定第三方 Release URL。

**PyInstaller 收集**：`pyinstaller-hooks-contrib` 中**不存在** pyzbar hook（已核实）。因此 `.spec` 必须显式收集，否则 DLL 不会进 exe：
```python
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules
binaries = collect_dynamic_libs('pyzbar')   # -> [('…/pyzbar/libzbar-64.dll','pyzbar'), ('…/libiconv.dll','pyzbar')]
```
这样 DLL 落入打包后的 `pyzbar/` 子目录，运行时（onefile 解压到 `_MEIPASS`）pyzbar 能在 `Path(__file__).parent` 找到。

**Linux 侧不受影响**：当前 Linux venv 的 `.pth`/shim 仅本地开发用且被 gitignore，不进入 CI 产物。

---

## 4. 交付物（提交到仓库）

| 文件 | 职责 |
|---|---|
| `.github/workflows/build-windows.yml` | CI 工作流：装环境→打包→冒烟测试→上传 Artifact→（tag 时）发布 Release |
| `packaging/qrtrans.spec` | PyInstaller 配置：onefile/console/收集 pyzbar DLL/hidden-imports |
| `docs/packaging-windows.md` | GitHub 仓库从零配置 + 触发构建 + 下载 exe + 验证清单 |
| `README.md`（增补） | "Windows 打包"小节，链接到上述文档 |

---

## 5. PyInstaller `.spec` 设计

`packaging/qrtrans.spec`：
- 入口脚本：`qrtrans/__main__.py`
- `binaries = collect_dynamic_libs('pyzbar')`（关键）
- `hiddenimports = collect_submodules('pyzbar') + collect_submodules('qrcode') + ['PIL']`
- onefile 模式（`EXE(...)` 直接接 `a.binaries/a.datas`，无 `COLLECT`）
- `console=True`（CLI 工具保留控制台）
- `upx=False`（UPX 压缩常引发杀软误报，关闭）
- `name='qrtrans'`
- `icon=None`（无自定义图标；如日后提供 `.ico` 可在此指定）
- 输出：`dist/qrtrans.exe`（预计 30–50MB）

---

## 6. CI 工作流设计（`.github/workflows/build-windows.yml`）

**触发**：
- `workflow_dispatch`（手动，Actions 页面点 "Run workflow"）
- `push.tags: ['v*']`（打版本 tag 自动构建并附到 Release）

**作业**（`runs-on: windows-latest`）步骤：
1. `actions/checkout@v4`
2. `actions/setup-python@v5`（Python 3.12）
3. `pip install --upgrade pip` → `pip install ".[dev]" pyinstaller`（pyzbar 自动取 win_amd64 wheel 带 DLL）
4. `pyinstaller packaging/qrtrans.spec --noconfirm`（产物 `dist/qrtrans.exe`）
5. **CI 内冒烟测试**（关键，提前发现 DLL 未收集等问题）：
   - `.\dist\qrtrans.exe --help` 退出码 0
   - ASCII 往返：encode 一段文本 → decode → 用 PowerShell 比对内容一致（避免 PS 编码问题，仅用 ASCII；CJK 由用户本地验收）
6. `actions/upload-artifact@v4` 上传 `dist/qrtrans.exe`（artifact 名 `qrtrans-windows-exe`）
7. **tag 触发时**：`softprops/action-gh-release@v2` 把 `dist/qrtrans.exe` 附加到对应 Release

**失败策略**：任一步骤失败工作流标红，用户在 Actions 页看日志排错。

---

## 7. GitHub 仓库配置步骤（写入 `docs/packaging-windows.md`，手把手）

1. **建仓库**：github.com → New repository → 名 `qrtrans`（或自定）→ **Public** → **不勾** Add README / .gitignore / license（避免与本地冲突）→ Create。
2. **认证**（三选一，推荐第 1 个）：
   - GitHub CLI：`gh auth login`（浏览器授权，最省事；如未装 `sudo apt install gh` 或访问 https://cli.github.com）。
   - SSH 密钥：生成 `ssh-keygen`，把公钥贴到 GitHub→Settings→SSH keys；remote 用 `git@github.com:<you>/qrtrans.git`。
   - Personal Access Token：GitHub→Settings→Developer settings→PAT（勾 `repo`）；push 时用 token 当密码。
3. **关联并推送**（本地仓库根目录执行）：
   ```
   git remote add origin https://github.com/<你>/qrtrans.git   # 或 SSH 地址
   git branch -M main           # 把 master 改名 main（与 GitHub 默认一致，可选）
   git push -u origin main
   ```
4. **触发构建**：
   - 手动：GitHub 仓库 → Actions → 左侧 `build-windows-exe` → Run workflow → 选 main 分支 → 运行。
   - 或版本构建：`git tag v0.1.0 && git push --tags`（自动构建并出 Release）。
5. **下载 exe**：
   - 手动构建：Actions → 点进对应运行 → 拉到底 Artifacts → `qrtrans-windows-exe` → 下载 zip 解压得 `qrtrans.exe`。
   - tag 构建：仓库 Releases 页面直接下载 `qrtrans.exe`。

> 国内访问 GitHub push/下载偶有波动；若持续困难可后续考虑镜像或 Gitee（但 Gitee Windows CI 免费额度有限，GitHub 最稳，本次不展开）。

---

## 8. 用户验收清单（在真实 Windows 机上）

下载 `qrtrans.exe` 后：
1. `qrtrans.exe --help` → 打印用法、退出 0。
2. `qrtrans.exe encode note.txt -o out\` → 生成 PNG（默认 array 帧）。
3. `qrtrans.exe decode out\ -o dec.txt` → 内容与 `note.txt` 一致。
4. 中文/emoji 往返：encode 含 `你好 🎉` 的文件 → decode → 一致。
5. 目录往返：encode 一个含子目录+空目录的目录 → decode → 结构与内容一致。
6. 把 `qrtrans.exe` 拷到其他目录运行 → 不依赖工作目录（验证 DLL 已正确内嵌，非外部依赖）。
7. （可接受）首次运行若杀软拦截，加白名单。

---

## 9. 已知限制

- **onefile 启动慢**：每次运行解压到临时目录，首次约 1–3 秒。可接受（偶尔传输场景）。日后嫌慢可改 onedir。
- **杀软误报**：可能被 Defender/SmartScreen 标记，需加白名单（用户已确认可接受）。`upx=False` 已尽量降低概率。
- **VC++ 运行时**：libzbar DLL 可能依赖 VC++ Redistributable，Windows 10/11 通常自带；极少数缺省环境需另装。
- **构建产物大小**：约 30–50MB（含 Python 解释器 + Pillow + 依赖）。
- **无法在 Linux 本地验证 Windows 产物**：CI 冒烟测试（步骤 5）能在 windows-latest 上提前发现问题；最终仍以用户在真实 Windows 上的 §8 验收为准。

---

## 10. 未来扩展（不在本次范围）
- 代码签名（减少杀软误报）。
- 32 位（x86）构建矩阵。
- onedir 模式（启动快、体积略大）。
- 自动发布到其他平台（Gitee Releases 镜像等）。
- 自定义图标。
