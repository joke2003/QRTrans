import subprocess
import sys
from pathlib import Path

def _run(args, **kw):
    return subprocess.run(
        [sys.executable, "-m", "qrtrans", *args],
        capture_output=True, text=True, **kw,
    )

def test_cli_help_encode(tmp_path):
    r = _run(["encode", "--help"])
    assert r.returncode == 0
    assert "--mode" in r.stdout
    assert "--grid" in r.stdout

def test_cli_roundtrip_array(tmp_path):
    src = tmp_path / "n.txt"
    src.write_text("cli roundtrip 🎉", encoding="utf-8")
    out = tmp_path / "out"
    decoded = tmp_path / "dec.txt"
    r1 = _run(["encode", str(src), "-o", str(out), "--mode", "array", "--batch", "11223344"])
    assert r1.returncode == 0, r1.stderr
    r2 = _run(["decode", str(out), "-o", str(decoded)])
    assert r2.returncode == 0, r2.stderr
    assert decoded.read_text(encoding="utf-8") == "cli roundtrip 🎉"

def test_cli_custom_aggressive_grid(tmp_path):
    src = tmp_path / "big.txt"
    src.write_text("K" * 14000, encoding="utf-8")  # 11 块 -> 首帧 10 个
    out = tmp_path / "out"
    r = _run(["encode", str(src), "-o", str(out),
              "--mode", "array", "--module-px", "2", "--grid", "5x2",
              "--no-label", "--batch", "aabbccdd"])
    assert r.returncode == 0, r.stderr
    frames = list(out.glob("qrtrans_aabbccdd_frame_*.png"))
    assert frames
    from PIL import Image
    from qrtrans.qr_scan import scan
    counts = [len(scan(Image.open(f))) for f in frames]
    assert max(counts) == 10

def test_cli_invalid_screen_format_errors(tmp_path):
    src = tmp_path / "n.txt"; src.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    r = _run(["encode", str(src), "-o", str(out), "--screen", "bad"])
    assert r.returncode == 2

def test_cli_nonexistent_input_errors(tmp_path):
    out = tmp_path / "out"
    r = _run(["encode", str(tmp_path / "nope.txt"), "-o", str(out)])
    assert r.returncode == 2

def test_cli_decode_partial_returns_nonzero(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("A" * 3000, encoding="utf-8")
    (root / "b.txt").write_text("B", encoding="utf-8")
    out = tmp_path / "out"
    _run(["encode", str(root), "-o", str(out), "--mode", "single", "--batch", "ffffffff"])
    pngs = sorted(out.glob("*.png"))
    pngs[0].unlink()
    dest = tmp_path / "dec"
    r = _run(["decode", str(out), "-o", str(dest)])
    assert r.returncode == 1  # partial success

def test_cli_encode_progress_to_stderr(tmp_path):
    # subprocess 捕获 stderr → 非 tty → 仅打阶段完成行（无 \r 刷新），且不污染 stdout
    src = tmp_path / "big.txt"
    src.write_text("X" * 4000)  # 多块 -> 多帧
    out = tmp_path / "out"
    r = _run(["encode", str(src), "-o", str(out), "--batch", "cliprog1"])
    assert r.returncode == 0, r.stderr
    assert "写帧" in r.stderr
    assert "\r" not in r.stderr          # 非 tty 不应有 \r 刷新
    assert "写帧" not in r.stdout        # 进度不污染 stdout


def test_cli_decode_progress_to_stderr(tmp_path):
    src = tmp_path / "n.txt"
    src.write_text("hello progress")
    out = tmp_path / "out"
    _run(["encode", str(src), "-o", str(out), "--batch", "dcliprog1"])
    dec = tmp_path / "dec.txt"
    r = _run(["decode", str(out), "-o", str(dec)])
    assert r.returncode == 0, r.stderr
    assert ("扫描" in r.stderr) or ("还原" in r.stderr)
    assert "\r" not in r.stderr
    assert dec.read_text(encoding="utf-8") == "hello progress"


def test_cli_default_mode_is_colormatrix(tmp_path):
    src = tmp_path / "n.txt"; src.write_text("default mode")
    out = tmp_path / "o"; dec = tmp_path / "d.txt"
    r = _run(["encode", str(src), "-o", str(out), "--batch", "cdef0001"])
    assert r.returncode == 0, r.stderr
    assert list(out.glob("qrtrans_cdef0001_cm_*.png"))   # colormatrix 命名


def test_cli_colormatrix_roundtrip(tmp_path):
    src = tmp_path / "n.txt"; src.write_text("cli cm 你好")
    out = tmp_path / "o"; dec = tmp_path / "d.txt"
    assert _run(["encode", str(src), "-o", str(out), "--batch", "clicm001"]).returncode == 0
    assert _run(["decode", str(out), "-o", str(dec)]).returncode == 0
    assert dec.read_text(encoding="utf-8") == "cli cm 你好"


def test_cli_colormatrix_custom_colors_cellpx(tmp_path):
    src = tmp_path / "n.txt"; src.write_text("x" * 500)
    out = tmp_path / "o"
    r = _run(["encode", str(src), "-o", str(out), "--colors", "32", "--cell-px", "5",
              "--batch", "cmcust01"])
    assert r.returncode == 0, r.stderr


def test_cli_qr_mode_still_works(tmp_path):
    src = tmp_path / "n.txt"; src.write_text("qr still ok")
    out = tmp_path / "o"; dec = tmp_path / "d.txt"
    r = _run(["encode", str(src), "-o", str(out), "--mode", "array", "--batch", "qrok0001"])
    assert r.returncode == 0
    assert list(out.glob("qrtrans_qrok0001_frame_*.png"))   # QR array 命名


def test_cli_qr_default_grid_is_4x2(tmp_path):
    # 不传 --grid，QR array 默认 4x2
    src = tmp_path / "big.txt"; src.write_text("K" * 14000)
    out = tmp_path / "o"
    _run(["encode", str(src), "-o", str(out), "--mode", "array", "--batch", "grid42001"])
    from PIL import Image
    from qrtrans.qr_scan import scan
    frames = list(out.glob("qrtrans_grid42001_frame_*.png"))
    assert max(len(scan(Image.open(f))) for f in frames) == 8   # 4x2=8


def test_cli_colormatrix_no_compress_roundtrip(tmp_path):
    src = tmp_path / "n.txt"; src.write_text("no compress 你好")
    out = tmp_path / "o"; dec = tmp_path / "d.txt"
    assert _run(["encode", str(src), "-o", str(out), "--no-compress", "--batch", "nocom001"]).returncode == 0
    assert _run(["decode", str(out), "-o", str(dec)]).returncode == 0
    assert dec.read_text(encoding="utf-8") == "no compress 你好"


def test_cli_colormatrix_missing_frame_fails(tmp_path):
    src = tmp_path / "big.txt"; src.write_text("Z" * 20000)
    out = tmp_path / "o"
    _run(["encode", str(src), "-o", str(out), "--no-compress", "--batch", "miss0001"])
    pngs = sorted(out.glob("*.png")); pngs[0].unlink()
    r = _run(["decode", str(out), "-o", str(tmp_path / "dec.txt")])
    assert r.returncode != 0
    assert "missing" in r.stderr.lower() or "error" in r.stderr.lower()


def test_cli_default_mode_roundtrip(tmp_path):
    # 默认 mode 下端到端可用（不只看文件名）
    src = tmp_path / "n.txt"; src.write_text("default rt")
    out = tmp_path / "o"; dec = tmp_path / "d.txt"
    assert _run(["encode", str(src), "-o", str(out), "--batch", "dfrt0001"]).returncode == 0
    assert _run(["decode", str(out), "-o", str(dec)]).returncode == 0
    assert dec.read_text(encoding="utf-8") == "default rt"


def test_cli_decode_mixed_types_fails(tmp_path):
    # cm 帧与一个无关 PNG 混在目录 → 报错（不静默走错路径）
    src = tmp_path / "n.txt"; src.write_text("mix")
    out = tmp_path / "o"
    _run(["encode", str(src), "-o", str(out), "--batch", "mix00001"])  # 产 cm 帧
    # 加一张无关白图
    from PIL import Image
    Image.new("RGB", (50, 50), "white").save(out / "zzz_noise.png")
    r = _run(["decode", str(out), "-o", str(tmp_path / "dec.txt")])
    assert r.returncode != 0
    assert "mixed" in r.stderr.lower()


def test_cli_encode_reads_viewer_config_for_screen(tmp_path, monkeypatch):
    import json
    monkeypatch.chdir(tmp_path)
    (tmp_path / "qrtrans.json").write_text(json.dumps({"screen": [800, 600]}))
    src = tmp_path / "n.txt"; src.write_text("config screen")
    out = tmp_path / "o"
    r = _run(["encode", str(src), "-o", str(out), "--no-label", "--batch", "cfg00001"])
    assert r.returncode == 0, r.stderr
    from PIL import Image
    p = next(out.glob("*.png"))
    with Image.open(p) as im:
        assert im.size == (800, 600)


def test_cli_encode_explicit_screen_overrides_config(tmp_path, monkeypatch):
    import json
    monkeypatch.chdir(tmp_path)
    (tmp_path / "qrtrans.json").write_text(json.dumps({"screen": [800, 600]}))
    src = tmp_path / "n.txt"; src.write_text("explicit")
    out = tmp_path / "o"
    r = _run(["encode", str(src), "-o", str(out), "--no-label",
              "--screen", "640x480", "--batch", "exp00001"])
    assert r.returncode == 0
    from PIL import Image
    p = next(out.glob("*.png"))
    with Image.open(p) as im:
        assert im.size == (640, 480)
