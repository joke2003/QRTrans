import argparse
import sys
from pathlib import Path


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="qrtrans-viewer",
        description="全屏图片序列播放器（为 colormatrix/QR 帧优化：真全屏 1:1、键盘切换、按间隔自动切换）",
    )
    p.add_argument("target", type=Path, help="目录或单图")
    p.add_argument("--interval", type=float, default=3.0, help="自动切换间隔秒（默认 3.0）")
    p.add_argument("--loop", action="store_true", help="末张后循环")
    p.add_argument("--no-overlay", dest="overlay", action="store_false", default=True,
                   help="关闭角标")
    args = p.parse_args(argv)
    if not args.target.exists():
        from .gui import report_error   # 错误路径才 import（tkinter 在 frozen viewer 里可用）
        report_error(f"not found: {args.target}")
        return 2
    # 延迟 import：仅在真正启动时才加载 Tk
    from .gui import run
    return run(args.target, args.interval, args.loop, args.overlay)


if __name__ == "__main__":
    sys.exit(main())
