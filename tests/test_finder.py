import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from qrtrans.finder import draw_markers, locate_markers, interior_box, MARKER_COLOR, MARKER_CELL


def test_draw_then_locate_four_corners():
    img = Image.new("RGB", (200, 150), "white")
    draw_markers(img, cell_px=4)
    corners = locate_markers(img)
    assert corners is not None and len(corners) == 4
    xs = sorted(c[0] for c in corners)
    ys = sorted(c[1] for c in corners)
    assert xs[0] < xs[-1] and ys[0] < ys[-1]


def test_locate_returns_none_when_absent():
    img = Image.new("RGB", (200, 150), "white")
    assert locate_markers(img) is None


def test_locate_with_interior_black_cells():
    # 关键回归：内部含大量黑色块（模拟真实帧的黑色单元格），标记色不应被混淆
    img = Image.new("RGB", (400, 300), "white")
    d = ImageDraw.Draw(img)
    for x in range(50, 380, 18):
        for y in range(50, 280, 18):
            d.rectangle([x, y, x + 14, y + 14], fill=(0, 0, 0))
    draw_markers(img, cell_px=8)   # 角标记画在最外角（覆盖部分内部黑块位置没关系）
    corners = locate_markers(img)
    assert corners is not None and len(corners) == 4
    TL = corners[0]
    # TL 必须在左上角附近、不被内部黑块拉偏
    assert TL[0] < 40 and TL[1] < 40


def test_locate_precision():
    img = Image.new("RGB", (400, 300), "white")
    draw_markers(img, cell_px=8)
    tl, tr, bl, br = locate_markers(img)
    half = (MARKER_CELL * 8) // 2
    assert abs(tl[0] - half) <= 4 and abs(tl[1] - half) <= 4
    assert abs(tr[0] - (400 - 1 - half)) <= 6 and abs(tr[1] - half) <= 4
    assert abs(bl[0] - half) <= 4 and abs(bl[1] - (300 - 1 - half)) <= 6
    assert abs(br[0] - (400 - 1 - half)) <= 6 and abs(br[1] - (300 - 1 - half)) <= 6


def test_interior_box_inside_and_uses_all_corners():
    img = Image.new("RGB", (400, 300), "white")
    draw_markers(img, cell_px=8)
    corners = locate_markers(img)
    x0, y0, x1, y1 = interior_box(corners, cell_px=8)
    assert 0 < x0 < x1 < 400 and 0 < y0 < y1 < 300


@pytest.mark.parametrize("scale", [0.85, 0.95, 1.05, 1.15])
def test_locate_survives_scales(scale):
    img = Image.new("RGB", (400, 300), "white")
    draw_markers(img, cell_px=8)
    scaled = img.resize((int(400 * scale), int(300 * scale)), Image.BILINEAR)
    corners = locate_markers(scaled)
    assert corners is not None and len(corners) == 4


def test_locate_precision_large_image():
    # 回归：2560 宽图下 step=min(W,H)//200=7，粗采样质心曾偏移 >2px
    # （marker 12px、采样 {0,7}→质心 3，真中心 5.5），是 cm 大屏解码失败的根因。
    W, H = 2560, 1440
    img = Image.new("RGB", (W, H), "white")
    draw_markers(img, cell_px=4)
    tl, tr, bl, br = locate_markers(img)
    half = (MARKER_CELL * 4) // 2  # 6；marker 真中心 ≈ half 与 W-1-half
    assert abs(tl[0] - half) <= 1 and abs(tl[1] - half) <= 1
    assert abs(tr[0] - (W - 1 - half)) <= 1 and abs(tr[1] - half) <= 1
    assert abs(bl[0] - half) <= 1 and abs(bl[1] - (H - 1 - half)) <= 1
    assert abs(br[0] - (W - 1 - half)) <= 1 and abs(br[1] - (H - 1 - half)) <= 1


def test_locate_resists_interior_false_positives_real_frame():
    # 回归（真实帧）：内部接近 marker 绿的单元曾把象限质心拉偏，顶左/顶右 marker
    # 被认成内部假阳性 → header 解不出 → 该帧被误判为"缺失帧 [5]"。
    # 真 marker 是密集实心块（~150-210px），假阳性是稀疏散点；取密度最高者。
    img = Image.open(Path(__file__).parent / "fixtures" / "cm_locate_false_positive.png").convert("RGB")
    W, H = img.size
    corners = locate_markers(img)
    assert corners is not None and len(corners) == 4
    tl, tr, bl, br = corners
    # 真 marker 在四角、构成规整矩形；假阳性会让顶边歪斜（旧代码 TL.y=80 TR.y=50）
    assert abs(tl[1] - tr[1]) <= 3, f"顶边歪斜: TL.y={tl[1]} TR.y={tr[1]}"
    assert abs(bl[1] - br[1]) <= 3
    assert tl[0] < W * 0.1 and tl[1] < H * 0.1
    assert tr[0] > W * 0.9 and tr[1] < H * 0.1
    # 整帧必须能解出（最终目标）
    from qrtrans.cm_decoder import _decode_one_frame
    assert _decode_one_frame(img) is not None, "fixture 帧应能完整解出"


def test_locate_picks_dense_corner_over_interior_scatter():
    # 合成：象限内撒大量散点假阳性绿（模拟缩放/捕获产生的内部绿点），
    # locate_markers 应选密集实心的真 marker（四角），而非被散点质心拉偏。
    import random
    W, H = 1600, 1200
    img = Image.new("RGB", (W, H), "white")
    draw_markers(img, cell_px=4)   # 四角 12px 实心 marker（中心 ~6,6 等）
    d = ImageDraw.Draw(img)
    random.seed(0)
    for _ in range(250):   # TL 象限内部散点假阳性（2x2 小块，密集度远低于实心 marker）
        x = random.randint(200, W // 2 - 20)
        y = random.randint(200, H // 2 - 20)
        d.rectangle([x, y, x + 1, y + 1], fill=MARKER_COLOR)
    tl, tr, bl, br = locate_markers(img)
    assert tl[0] < 40 and tl[1] < 40, f"TL={tl} 被散点拉偏（真 marker 应在 ~6,6）"
    assert tr[0] > W - 40 and tr[1] < 40
    assert bl[0] < 40 and bl[1] > H - 40
    assert br[0] > W - 40 and br[1] > H - 40
