# QRTrans Windows 打包实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 用 GitHub Actions（`windows-latest`）把 QRTrans 打包成单个 Windows x64 `qrtrans.exe`，产物作为 CI Artifact / Release 提供。

**架构：** PyInstaller `--onefile --console`；libzbar DLL 由 pyzbar 的 Windows wheel 自带，`.spec` 用 `collect_dynamic_libs('pyzbar')` 收集（已核实无第三方 hook）。CI 内置冒烟+往返测试提前发现问题。

**技术栈：** PyInstaller ≥6、GitHub Actions（setup-python/checkout/upload-artifact/softprops-action-gh-release）。

**参考规格：** `docs/superpowers/specs/2026-06-18-windows-packaging-design.md`

**验证策略说明：** PyInstaller 不能跨平台，本地（Linux）只能验证 `.spec` 语法与 import 图（产出 Linux 二进制，解码侧因无系统 libzbar 不可用，仅验 `--help`/encode）；**Windows DLL 收集与往返的真正验证在 CI 的 windows-latest 上完成**，最终由用户在真实 Windows 上按规格 §8 验收。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `packaging/qrtrans.spec` | PyInstaller 配置：onefile/console/收集 pyzbar DLL/hidden-imports |
| `.github/workflows/build-windows.yml` | CI 工作流：装环境→打包→冒烟往返→上传 Artifact→tag 时发 Release |
| `docs/packaging-windows.md` | GitHub 仓库从零配置 + 触发 + 下载 + 验收清单（手把手） |
| `README.md`（增补） | "Windows 打包"小节 |

---

## 任务 1：PyInstaller `.spec` + 本地冒烟

**文件：**
- 创建：`packaging/qrtrans.spec`

- [ ] **步骤 1：编写 `packaging/qrtrans.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-
# QRTrans Windows 单 exe 打包配置（也兼容 Linux 本地冒烟构建）
# libzbar 的 DLL 由 pyzbar 的 Windows wheel 自带；这里显式收集，
# 因为 pyinstaller-hooks-contrib 中不存在 pyzbar hook（已核实）。
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

binaries = collect_dynamic_libs('pyzbar')   # Windows: libzbar-64.dll, libiconv.dll
hiddenimports = (
    collect_submodules('pyzbar')
    + collect_submodules('qrcode')
    + ['PIL']
)

a = Analysis(
    ['qrtrans/__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='qrtrans',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX 常引发杀软误报，关闭
    runtime_tmpdir=None,
    console=True,               # CLI 工具保留控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
```

> 实现者注：若本地 PyInstaller 版本对 `EXE` 形参有差异导致构建失败，以 `pyi-makespec --onefile --console --name qrtrans qrtrans/__main__.py` 生成的 spec 为基线，再把 `binaries`/`hiddenimports` 两项合并进去。务必保证构建成功。

- [ ] **步骤 2：本地安装 pyinstaller**

运行：`.venv/bin/python -m pip install pyinstaller`

- [ ] **步骤 3：本地冒烟构建（验证 spec 语法与 import 图）**

运行：`.venv/bin/pyinstaller packaging/qrtrans.spec --noconfirm`
预期：生成 `dist/qrtrans`（Linux 二进制），无 spec 语法/import 错误。允许有 warnings，但不得有 fatal error。

- [ ] **步骤 4：确认产物可引导（仅 `--help`，不测 decode）**

运行：`./dist/qrtrans --help`
预期：打印用法、退出码 0。
> 说明：本地 Linux 产物不含 libzbar（Linux pyzbar wheel 无 DLL），decode 会失败；encode 不依赖 pyzbar 故可用。Windows DLL 收集的正确性由 CI 验证（任务 2/4）。

- [ ] **步骤 5：清理构建产物，避免污染 git**

```bash
echo "/dist/" >> .gitignore
echo "/build/" >> .gitignore
echo "*.spec.bak" >> .gitignore
rm -rf dist build
git status   # 确认 dist/、build/ 不出现
```

- [ ] **步骤 6：Commit**

```bash
git add packaging/qrtrans.spec .gitignore
git commit -m "feat(packaging): add PyInstaller spec for windows single-exe build"
```

---

## 任务 2：GitHub Actions 工作流

**文件：**
- 创建：`.github/workflows/build-windows.yml`

- [ ] **步骤 1：编写 `.github/workflows/build-windows.yml`**

```yaml
name: build-windows-exe

on:
  workflow_dispatch:
  push:
    tags:
      - 'v*'

permissions:
  contents: write   # tag 触发时 softprops/action-gh-release 需要写 Release 权限

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        shell: pwsh
        run: |
          python -m pip install --upgrade pip
          pip install ".[dev]" pyinstaller

      - name: Build exe
        shell: pwsh
        run: pyinstaller packaging/qrtrans.spec --noconfirm

      - name: Smoke + roundtrip test (ASCII)
        shell: pwsh
        run: |
          .\dist\qrtrans.exe --help
          if ($LASTEXITCODE -ne 0) { Write-Error "--help failed"; exit 1 }
          $tmp = "$env:TEMP\qrt_smoke"
          New-Item -ItemType Directory -Force -Path $tmp | Out-Null
          Set-Content -Path "$tmp\in.txt" -Value "qrtrans ci smoke 12345"
          .\dist\qrtrans.exe encode "$tmp\in.txt" -o "$tmp\out" --batch cismoke1
          if ($LASTEXITCODE -ne 0) { Write-Error "encode failed"; exit 1 }
          .\dist\qrtrans.exe decode "$tmp\out" -o "$tmp\dec.txt"
          if ($LASTEXITCODE -ne 0) { Write-Error "decode failed"; exit 1 }
          $a = (Get-Content "$tmp\in.txt" -Raw).Trim()
          $b = (Get-Content "$tmp\dec.txt" -Raw).Trim()
          if ($a -ne $b) { Write-Error "roundtrip mismatch: '$a' vs '$b'"; exit 1 }
          Write-Host "roundtrip OK"

      - uses: actions/upload-artifact@v4
        with:
          name: qrtrans-windows-exe
          path: dist/qrtrans.exe
          if-no-files-found: error

      - name: Attach to Release (on tag)
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: dist/qrtrans.exe
```

- [ ] **步骤 2：校验 YAML 语法**

运行：`.venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/build-windows.yml')); print('YAML OK')"`
预期：`YAML OK`（若 venv 无 pyyaml，`.venv/bin/python -m pip install pyyaml -q` 再跑）。

- [ ] **步骤 3：Commit**

```bash
git add .github/workflows/build-windows.yml
git commit -m "ci: add windows single-exe build workflow"
```

---

## 任务 3：打包文档 + README 小节

**文件：**
- 创建：`docs/packaging-windows.md`
- 修改：`README.md`

- [ ] **步骤 1：编写 `docs/packaging-windows.md`**

````markdown
# QRTrans Windows 单 exe 打包指南

QRTrans 通过 GitHub Actions 在 `windows-latest` 上构建单个 Windows `qrtrans.exe`，你无需本地 Windows 或 Python。libzbar 的 DLL 由 pyzbar 的 Windows wheel 自带，工作流自动处理。

## 1. 在 GitHub 创建仓库

1. 打开 https://github.com/new
2. Repository name：`qrtrans`（或自定）
3. 选 **Public**（Actions 免费额度无限）
4. **不要勾** "Add a README" / ".gitignore" / "license"（避免与本地已有提交冲突）
5. 点 Create repository

## 2. 配置认证（三选一，推荐 GitHub CLI）

**推荐：GitHub CLI**
```bash
# 装好后（Linux: sudo apt install gh；或访问 https://cli.github.com）
gh auth login          # 选 GitHub.com → HTTPS → 浏览器授权
```

**或：SSH 密钥**
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
cat ~/.ssh/id_ed25519.pub    # 把内容贴到 GitHub → Settings → SSH and GPG keys → New SSH key
```

**或：Personal Access Token**
- GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token，勾 `repo` 权限。push 时用户名填你的 GitHub 名，密码填该 token。

## 3. 关联并推送本地仓库

在项目根目录 `/home/kanshan/projects/QRTrans`：

```bash
git remote add origin https://github.com/<你的用户名>/qrtrans.git
# 用 SSH 则：git remote add origin git@github.com:<你的用户名>/qrtrans.git
git branch -M main          # 把 master 改名为 main（与 GitHub 默认一致）
git push -u origin main
```

> 若 `gh auth login` 已完成，push 不会要求密码；用 SSH 需先完成第 2 步密钥；用 token 则按提示粘贴。

## 4. 触发构建

**方式 A：手动构建（取 Artifact）**
- 仓库页 → **Actions** → 左侧选 `build-windows-exe` → 右侧 **Run workflow** → 选 `main` 分支 → 点 Run workflow。
- 等运行变绿（约 3–6 分钟）。

**方式 B：版本构建（取 Release）**
```bash
git tag v0.1.0
git push --tags
```
- 工作流自动构建并把 `qrtrans.exe` 附加到该版本的 Release。

## 5. 下载 exe

- **手动构建**：Actions → 点进那次运行 → 滚到底 **Artifacts** → `qrtrans-windows-exe` → 下载 zip → 解压得 `qrtrans.exe`。
- **版本构建**：仓库首页右侧 **Releases** → 对应版本 → 下载 `qrtrans.exe`。

## 6. 在 Windows 上验收

把 `qrtrans.exe` 拷到任意目录，打开 cmd 或 PowerShell：

```powershell
qrtrans.exe --help
qrtrans.exe encode note.txt -o out\
qrtrans.exe decode out\ -o dec.txt
```

验收清单：
1. `--help` 打印用法、退出 0。
2. 含中文/emoji 的文件 encode→decode 内容一致。
3. 含子目录+空目录的目录 encode→decode 结构与内容一致。
4. 把 `qrtrans.exe` 拷到其他目录仍能运行（验证 libzbar DLL 已内嵌，不依赖外部）。
5. 首次运行若 Defender 拦截，加白名单（PyInstaller exe 常见误报）。

## 排错

- **工作流红**：Actions → 点进失败运行 → 看哪一步失败。常见：spec 变更后 `pyinstaller` 报错（修 `packaging/qrtrans.spec`）、smoke roundtrip 不一致（DLL 未收集 → 检查 `collect_dynamic_libs('pyzbar')`）。
- **decode 失败、提示找不到 zbar**：DLL 未被打包，确认 `.spec` 含 `binaries = collect_dynamic_libs('pyzbar')`。
- **杀软拦截**：加白名单；或日后考虑 Nuitka/代码签名。
- **国内 push/下载慢**：GitHub 偶有波动，多试或换网络；持续困难可留言评估切镜像。
````

- [ ] **步骤 2：README 增补 "Windows 打包" 小节**

在 `README.md` 末尾追加：

```markdown

## Windows 打包（单 exe）

通过 GitHub Actions 构建 Windows 单文件 `qrtrans.exe`，无需本地 Windows/Python。完整步骤（建仓库、认证、推送、触发、下载、验收、排错）见 [`docs/packaging-windows.md`](docs/packaging-windows.md)。

快速触发：推到 GitHub 后打 tag `git tag v0.1.0 && git push --tags`，工作流自动构建并在 Releases 发布 `qrtrans.exe`。
```

- [ ] **步骤 3：Commit**

```bash
git add docs/packaging-windows.md README.md
git commit -m "docs: add windows packaging guide and README section"
```

---

## 任务 4：用户驱动的 GitHub 验证（非代码，需你执行）

> 这一步由**用户**在 push 后触发，是 Windows DLL 收集与往返的**真正验证**。

- [ ] **步骤 1**：用户按 `docs/packaging-windows.md` §1–§3 创建 GitHub Public 仓库、配置认证、push 代码（`git remote add origin ... && git branch -M main && git push -u origin main`）。**需要时由用户执行（可能涉及 sudo 装 gh 或浏览器授权）。**
- [ ] **步骤 2**：用户触发手动构建（Actions → Run workflow），等待变绿。
- [ ] **步骤 3**：若工作流**失败**，由控制者读 Actions 日志、定位并修复 `packaging/qrtrans.spec` 或工作流，commit、push 重跑，直到变绿。
- [ ] **步骤 4**：用户下载 Artifacts 解压得 `qrtrans.exe`，在真实 Windows 上按规格 §8（`docs/packaging-windows.md` §6）执行验收清单。
- [ ] **步骤 5**：验收通过后，可选 `git tag v0.1.0 && git push --tags` 出首个 Release。

---

## 自检

### 1. 规格覆盖度
- §3 libzbar（pyzbar wheel 自带 DLL + `collect_dynamic_libs`）：任务 1 spec + 任务 2 CI 冒烟 ✓
- §5 PyInstaller 配置（onefile/console/upx=False/name/icon=None）：任务 1 ✓
- §6 CI 工作流（触发、装环境、打包、冒烟往返、artifact、tag release）：任务 2 ✓
- §7 GitHub 仓库配置步骤：任务 3 文档 + 任务 4 执行 ✓
- §8 用户验收清单：任务 3 文档 §6 + 任务 4 步骤 4 ✓
- §9 已知限制：文档排错章节体现 ✓
- 交付物（spec/workflow/docs/README）：全部对应 ✓

### 2. 占位符扫描
- 每个步骤含完整文件内容；`<你的用户名>` 为占位但属用户填入项（文档模板，已用 `<>` 标示），非规格缺陷 ✓
- 无 TODO/"待定" ✓

### 3. 类型/命名一致性
- spec 的 `collect_dynamic_libs('pyzbar')` 与规格 §3、§5 一致 ✓
- 工作流 `pyinstaller packaging/qrtrans.spec` 与任务 1 文件路径一致 ✓
- artifact 名 `qrtrans-windows-exe`、release 文件 `dist/qrtrans.exe` 在文档与工作流一致 ✓

### 4. 范围
- 单一聚焦功能（Windows 打包），3 个代码/文档任务 + 1 个用户验证任务，可由一个计划覆盖 ✓
