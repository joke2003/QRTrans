import os
import sys

# windowed (console=False) 冻结 exe 下 sys.stdout/stderr 为 None，
# 任何 print（含 argparse --help）会 AttributeError 崩溃。
# 在最早期把它们接到 devnull，保证不崩（用户面错误由 report_error 弹窗处理）。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")

from qrtrans_viewer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
