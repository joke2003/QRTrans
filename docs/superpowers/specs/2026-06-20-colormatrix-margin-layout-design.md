# Colormatrix 帧布局：修 label 裁切 + 四边留白

## 背景

Win11 实测发现：colormatrix 帧在 viewer 全屏显示时，**顶部两个 finder 标记被裁掉**。
根因：编码器令 `grid_h = screen_h`，再叠 40px label 横幅 → 帧高 = `screen_h + 40`，
viewer 把 taller 的图塞进 screen 高的 Label（Tk 不缩放、默认居中）→ 上下各裁 ~20px，
顶部 marker（帧 y=0..11）整块丢失。摄像头/截图只能看到 2/4 标记 → 解码失败。

同时用户希望帧四周留一点黑色边距，用于截图后划线标注、并抵御屏幕边框/截图工具的边缘裁切。

## 目标

1. **修 label 裁切**：colormatrix 帧总尺寸严格 == 目标屏幕尺寸，viewer 不再裁切。
2. **加四边黑色留白**：可配，默认 24px，仅 colormatrix 模式。
3. 解码器与 viewer **不改**（解码靠 marker 定位，与留白无关；viewer 只需帧==屏幕）。

## 设计

### 统一布局

帧 = `screen_w × screen_h`，内部从外到内：黑色 margin → grid(markers+cells) → label。

```
垂直： M(顶黑) + grid_h_px + L(label)  + 余量(并入底黑) = screen_h
水平： M(左黑) + grid_w_px              + M(右黑)        = screen_w
其中 L = 40 if label else 0
```

### 尺寸数学

- `grid_w = (screen_w - 2*margin) // cell_px`
- `grid_h = (screen_h - 2*margin - L) // cell_px`
- `grid_w_px = grid_w * cell_px`，`grid_h_px = grid_h * cell_px`（取整余量并入底部/右侧黑边）
- grid 绘制偏移 `(margin, margin)`；label 绘制于 `y = margin + grid_h_px`；canvas 其余填黑。
- marker 仍在 grid 四角（距屏边 margin）。

**默认 2560×1440、margin=24、label**：grid=628×338 cell，frame=2560×1440，
marker 在 (24,24) 等处，四角全在画面内、零裁切。

### 改动范围

- `qrtrans/cm_encoder.py`
  - `CmEncodeOptions`：加 `margin: int = 24`
  - `_grid_dims`：按 `(screen - 2*margin (- L)) // cell_px` 计算
  - `_render_frame`：canvas 改为 `screen_w × screen_h`、黑底；grid 贴到 `(margin, margin)`；label 下移
- `qrtrans/cli.py`：`encode` 加 `--margin`（int，默认 24，仅 colormatrix 用）
- 解码器、viewer、finder：**不动**

### 测试

1. frame 总尺寸 == screen（带 label、带 margin）
2. 四角 marker 坐标都在画面内（`margin ≤ x < screen_w - margin` 等）
3. 大屏 2560×1440 + label + margin 往返 OK（回归顶部裁切 bug）
4. `margin=0, label=False` 退化为原全填行为（向后兼容）
5. margin 过大致 grid 过小 → 现有 `too small` 报错仍生效

### 兼容性

- 默认 `margin=24`：帧自动 == screen（顺带修原 bug）。
- `--margin 0 --no-label`：完全恢复旧行为（grid 全填）。
- 解码向后兼容：旧帧（无留白、marker 在屏角）仍可解；新帧（有留白、marker 内缩）也可解。

## 非目标

- QR array/single 模式不加留白（本次仅 colormatrix）。
- viewer 侧不做缩放适配（会破坏 1:1 单元像素）。
