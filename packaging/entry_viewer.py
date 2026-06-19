import os
import sys

# entry_viewer.py 仅作 PyInstaller frozen 入口（windowed, console=False）。
# windowed 下 stdout/stderr 可能是 None 或 cp1252 编码的未知类型，
# 含中文的 argparse --help / print 都会崩。
# 无条件替换为 UTF-8 devnull（windowed 下输出本就不可见，这纯粹是防崩）。
# 开发模式（python -m qrtrans_viewer）不走此文件，不受影响。
sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")

from qrtrans_viewer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
