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
