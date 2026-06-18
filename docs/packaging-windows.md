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

- **工作流红**：Actions → 点进失败运行 → 看哪一步失败。常见：spec 变更后 `pyinstaller` 报错（修 `packaging/qrtrans.spec`）、smoke roundtrip 不一致（DLL 未收集 → 检查 `.spec` 里 `collect_dynamic_libs('pyzbar')` 与 `entry.py`）。
- **decode 失败、提示找不到 zbar**：DLL 未被打包，确认 `.spec` 含 `binaries = collect_dynamic_libs('pyzbar')`，且 `packaging/entry.py` 存在。
- **`--help` 崩溃、ImportError**：检查入口是否用了 `packaging/entry.py`（不要直接用 `qrtrans/__main__.py`，它的相对导入在打包后不可用）。
- **杀软拦截**：加白名单；或日后考虑 Nuitka / 代码签名。
- **国内 push/下载慢**：GitHub 偶有波动，多试或换网络；持续困难可留言评估切镜像。
