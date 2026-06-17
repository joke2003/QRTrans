from qrtrans.protocol import make_file_payload
from qrtrans.qr_render import render, CELL_MODULES, EC_LEVELS

def _payload(data_b64="SGVsbG8="):
    return make_file_payload(
        batch="abc12345", fid="f00", relpath="a.txt", fn="a.txt",
        ci=0, tc=1, sha256="d"*64, data_b64=data_b64,
    )

def test_render_returns_image_of_expected_size():
    from PIL import Image
    img = render(_payload(), module_px=3, ec="M")
    assert isinstance(img, Image.Image)
    expected = CELL_MODULES * 3   # 185 * 3 = 555
    assert img.size == (expected, expected)

def test_render_size_scales_with_module_px():
    img = render(_payload(), module_px=2, ec="M")
    assert img.size == (CELL_MODULES * 2, CELL_MODULES * 2)

def test_render_invalid_ec_raises():
    import pytest
    with pytest.raises(ValueError):
        render(_payload(), module_px=3, ec="X")

def test_render_data_overflow_raises():
    import pytest
    huge = "A" * 3000  # 超过 V40/M byte 容量 2331（即便 qrcode 选 alnum 也无关，
                       # 我们按 byte 容量拒绝）
    with pytest.raises(ValueError, match="capacity"):
        render(_payload(data_b64=huge), module_px=3, ec="M")

def test_render_near_capacity_succeeds():
    # JSON 字节数接近但不超过 V40/M byte 容量，应成功渲染
    p = _payload(data_b64="A" * 1700)   # JSON ~1908B < 2331
    img = render(p, module_px=3, ec="M")
    assert img.size == (CELL_MODULES * 3, CELL_MODULES * 3)
