from qrtrans.protocol import make_file_payload
from qrtrans.qr_render import render
from qrtrans.qr_scan import scan
from PIL import Image

def _payload():
    return make_file_payload(
        batch="abc12345", fid="f00", relpath="a.txt", fn="a.txt",
        ci=0, tc=1, sha256="d"*64, data_b64="SGVsbG8=",
    )

def test_scan_single_qr():
    img = render(_payload(), module_px=4, ec="M")
    payloads = scan(img)
    assert len(payloads) == 1
    assert payloads[0] == _payload()

def test_scan_image_without_qr_returns_empty():
    blank = Image.new("RGB", (200, 200), "white")
    assert scan(blank) == []

def test_scan_skips_non_qrt_qr(tmp_path):
    # 生成一个非 QRT 的普通 QR
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=4, border=4)
    qr.add_data("https://example.com/not-qrt")
    qr.make(fit=True)
    other = qr.make_image().get_image()
    assert scan(other) == []

def test_scan_multiple_qrs_in_one_image():
    # 阵列场景：一张图里多个 QR 都应被检出
    p1 = make_file_payload(batch="abc12345", fid="f00", relpath="a.txt", fn="a.txt",
                           ci=0, tc=2, sha256="d"*64, data_b64="AAA=")
    p2 = make_file_payload(batch="abc12345", fid="f00", relpath="a.txt", fn="a.txt",
                           ci=1, tc=2, sha256="d"*64, data_b64="BBB=")
    from qrtrans.qr_render import CELL_MODULES
    cell = CELL_MODULES * 4
    canvas = Image.new("RGB", (cell * 2, cell), "white")
    canvas.paste(render(p1, module_px=4, ec="M"), (0, 0))
    canvas.paste(render(p2, module_px=4, ec="M"), (cell, 0))
    payloads = scan(canvas)
    fids = sorted((pl.fid, pl.ci) for pl in payloads)
    assert fids == [("f00", 0), ("f00", 1)]
