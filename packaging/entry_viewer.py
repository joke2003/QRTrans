import os
import sys


def _ensure_utf8_stream(stream):
    """windowed 冻结 exe 下 stdout/stderr 可能为 None 或 cp1252 编码，
    两者都会让含中文的 argparse --help 崩溃。统一确保 UTF-8。"""
    if stream is None:
        return open(os.devnull, "w", encoding="utf-8", errors="replace")
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
    return stream


sys.stdout = _ensure_utf8_stream(sys.stdout)
sys.stderr = _ensure_utf8_stream(sys.stderr)

from qrtrans_viewer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
