# QRTrans Viewer（全屏播放器）设计规格

- **日期**：2026-06-19
- **状态**：待审查
- **关联**：`docs/superpowers/specs/2026-06-18-colormatrix-design.md`（colormatrix）；主程序设计

---

## 1. 目标与非目标

### 目标
提供一个独立的全屏图片序列播放器 `qrtrans-viewer`，针对 colormatrix（及 QR）帧的"显示→对端拍摄/截图"工作流优化：真全屏（用满每个像素、最大化密度）、目录内键盘切换、按间隔自动切换。**通用图片播放器，不耦合 qrtrans 内部**（不 import qrtrans/reedsolo/pyzbar）。

### 非目标（YAGNI）
- 不做视频/快切录屏传输模式（未来；本 viewer 是其底座）。
- 不做网络/远程传输。
- 不解析帧头（batch/frame 从文件名取）。
- 不做编辑/标注。

---

## 2. 架构

- **独立 exe** `qrtrans-viewer`（与 encode/decode 主 exe 解耦；主 exe 保持精简，不引入 Tcl/Tk）。
- **Tkinter + Pillow**（Tkinter 是 stdlib、Win7 兼容、PyInstaller 友好；**零新依赖**）。
- 通用：加载目录/单图 → 全屏 → 键盘/定时切换。对 QR 帧同样适用。
- 包结构：
  - `qrtrans_viewer/__init__.py`、`__main__.py`（入口）
  - `qrtrans_viewer/core.py`（**纯逻辑、可测**：图片列表/排序、当前索引、播放状态、间隔、advance 决策）
  - `qrtrans_viewer/gui.py`（Tkinter 接线层，薄）
  - `packaging/qrtrans_viewer.spec`（PyInstaller）

---

## 3. CLI / 入口

```
qrtrans-viewer <dir|image> [--interval <秒>] [--loop] [--no-overlay]
```
- `<dir|image>`：目录（加载其中所有图片，按名排序）或单图。
- `--interval`：自动切换间隔秒，默认 `3.0`，可小数（如 `0.5` 快档、`5` 慢档）。
- `--loop`：末张后循环回首页（默认关：末张停）。
- `--no-overlay`：关闭角标（默认开）。

退出码：`0` 正常退出（Esc）；`2` 输入错误（路径不存在/无图）。

---

## 4. 功能

### 显示
- **真全屏、无边框**：`root.attributes('-fullscreen', True)`；Win7 偶有留边时用 `overrideredirect(True)` + `geometry(WxH+0+0)` 兜底。
- **1:1 显示、不缩放、居中**：帧尺寸 ≠ 屏幕时留边（letterbox），**绝不缩放**（保单元格精度；缩放会致子像素→解码困难）。背景黑。
- 颜色忠实：Tk/PIL 显示不做 ICC 调色（对 colormatrix 是好事）。
- 预加载下一张（避免切换闪烁）。

### 键盘
| 键 | 动作 |
|---|---|
| `→` / `Space` | 下一张 |
| `←` | 上一张 |
| `P` | 播放/暂停自动切换 |
| `+` / `=` | 间隔 +0.5s |
| `-` | 间隔 −0.5s（下限 0.2s） |
| `O` | 角标开关 |
| `Home` / `End` | 首张 / 末张 |
| `Esc` / `Q` | 退出 |

### 自动切换
- `P` 启动后按当前间隔自动下一张；末张：`--loop` 则回首页，否则停并自动暂停。
- 间隔可 `+/-` 实时调；手动 `→/←` 不影响计时节奏（重置定时器）。

### 角标（默认开）
- 左下小字：`<文件名> · i/N · <间隔>s · ▶/⏸`；半透明或纯色底，不浪费主体像素。
- 启动首帧额外显示一行：`本机分辨率 WxH（编码请用 --screen WxH 匹配以 1:1 铺满）`，3 秒后淡出（便于非默认分辨率场景核对）。

### 写入本地 config（便携）
- **每次启动**把实测全屏分辨率写到 **当前工作目录** 的 `./qrtrans.json`：`{"screen": [W, H], "recorded_at": "<ISO8601>"}`。
- **best-effort**：只读目录/写失败时静默忽略，不影响播放。
- **位置选 CWD 而非用户家目录**：便携使用（exe + config + 数据同目录一锅端，如 U 盘），不污染家目录、不限账号；前提是 viewer 与 encoder 在**同一目录**运行（见 §5）。

---

## 5. 与 encoder 的协同（密度最大化，经 CWD 本地 config）

**拓扑**：encoder 与 viewer 跑在**同一台机器**（编码机 A：encoder 出图 + viewer 显示；对端 B 拍摄/截图 A 的屏）。config 是 A 本地文件，两者同目录即可互访。气隙下无跨机通信。

**机制（解决"viewer 报尺寸时 encoder 已跑完"的时序问题）**：
1. **viewer 每次启动**把实测全屏分辨率写到 **CWD 的 `./qrtrans.json`**（见 §4，best-effort）。viewer 实测值是**权威**（含 DPI/真全屏真实可绘区域），比 encoder 自猜屏分辨率更准。
2. **encoder**：启动时若用户**未显式传 `--screen`**，读取 `./qrtrans.json` 的 `screen` 作默认；文件不存在才回退 `1920x1080`。**显式 `--screen` 永远最高优先级**（覆盖 config）。
3. **正常流程**：首次在该目录开一次 viewer（哪怕几秒）→ 它记下分辨率 → 之后 encoder 自动用该值，无需记数字/手动传。

- 1080p 屏：默认就吻合、零浪费；非 1080p：开一次 viewer 后 encoder 自动适配。
- 不匹配时 viewer 仍 1:1 居中（留边），解码正确但密度略降。
- 若 encoder 与 viewer 不在同一目录/不同机器（罕见），config 够不着 → 回退手动 `--screen`。

> **impl 备注**：encoder 侧"读 `./qrtrans.json` 作 --screen 默认"是对 `qrtrans` CLI 的小改动（属于本特性的实现计划，不另立项）。

---

## 6. 实现要点与风险

- **Win7 全屏留边**：`-fullscreen` 为主、`overrideredirect+geometry` 兜底；CI/手测验证。
- **DPI 缩放**：禁用 Tk 缩放（`scaling` 设 1.0）或确保 1:1，避免单元错位。
- **定时**：`widget.after(ms, …)`；切图前预加载下一张 `PhotoImage`。
- **大图/多图内存**：仅缓存当前+下一张，不一次性加载全部。
- **退出收尾**：Esc 关闭窗口、释放资源。
- **GUI 可测性**：core 与 gui 分层；core 纯逻辑全单测；gui 层薄，靠手测/CI 冒烟。

---

## 7. 打包 / CI

- `packaging/qrtrans_viewer.spec`（PyInstaller onefile + windowed，**windowed** 模式避免弹控制台黑窗；hidden-imports：`tkinter`、`PIL.ImageTk`）。
- GHA 工作流加 viewer 构建 job（windows-latest，Python 3.8），产物 `qrtrans-viewer.exe`。
- 下个 release（v0.3.0）出**双 exe**：主 encode/decode + viewer。
- windowed 模式下 `print` 不可见；错误用 Tk 弹窗或退出码体现。

---

## 8. 测试策略

- **`qrtrans_viewer/core.py` 纯逻辑单测**（重点，TDD）：
  - 图片列表收集+排序（按名）、过滤非图。
  - 索引前进/后退/首末、越界钳制、循环开关下末张行为。
  - 间隔调整上下限、播放/暂停状态转移。
  - advance 决策（到点→下一张；暂停→不进）。
  - **config 读写**：`write_config(screen)` 写 `./qrtrans.json`（含 recorded_at）；`read_config()` 读回；坏 JSON/缺文件返回 None；只读目录 best-effort 不抛。
- **GUI 冒烟**：`subprocess` 启动 viewer 给定一个临时目录图、若干秒后杀进程、断言进程启动成功（退出码不等于"输入错误"）。需图形环境的深度 GUI 断言（截图比对）不在范围。
- **CLI**：`--interval`/`--loop`/`--no-overlay` 解析；非法路径退出码 2。

> GUI 在无头 Linux 上无法运行真 Tk；core 单测在 CI 全平台可跑；GUI 冒烟仅在 windows-latest runner 上做（或本地手测）。

---

## 9. 已知限制
- 1:1 不缩放：帧尺寸 > 屏幕时会被裁剪（边缘单元丢失）→ 编码时应使 `--screen` ≤ 实际屏。
- 角标占左下小块像素（可关）。
- 不解析帧内容（仅按文件名/排序位置显示元信息）。

---

## 10. 未来扩展（不在本次范围）
- 视频/快切录屏传输模式（间隔可降到 <1s，配合对端录屏）。
- 从帧头读 batch/frame_total（需引入 cm 解析，增加耦合，暂不做）。
- 跨目录播放列表、淡入淡出过渡。
