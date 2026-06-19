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

---

## 5. 与 encoder 的协同（密度最大化）

- encoder 默认 `--screen 1920x1080`；1080p 显示器上 viewer 真全屏 = 1920×1080 可用 → **默认即 1:1 铺满、零浪费**，无需手动配合。
- 非 1080p：viewer 启动横幅报告自身分辨率 → 用户在编码端传匹配 `--screen` → 1:1 铺满。
- 不匹配时 viewer 仍 1:1 居中（留边），解码正确但密度略降。
- **无跨机通信**（气隙）；纯"默认对齐 + 自报尺寸"。

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
