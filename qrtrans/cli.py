from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Sequence

from .decoder import decode, DecodeError, DecodeOptions
from .encoder import encode, EncodeOptions
from .fs_walk import FsError


_EXIT_OK = 0
_EXIT_PARTIAL = 1
_EXIT_FAIL = 2


_PROGRESS_LABELS = {
    "prepare": "准备",
    "frame": "写帧",
    "qr": "生成",
    "scan": "扫描",
    "reassemble": "还原",
}


def _make_progress_printer():
    is_tty = sys.stderr.isatty()

    def _print(ev):
        label = _PROGRESS_LABELS.get(ev.phase, ev.phase)
        if ev.total > 0:
            pct = ev.current * 100 // ev.total
            line = f"{label} {ev.current}/{ev.total} ({pct}%)"
        else:
            line = label
        if is_tty:
            sys.stderr.write("\r" + line + "   ")
            sys.stderr.flush()
            if ev.current == ev.total:
                sys.stderr.write("\n")
        else:
            # 非 tty（重定向/CI 捕获）：仅阶段完成时打一行，避免 \r 污染日志
            if ev.current == ev.total:
                sys.stderr.write(line + "\n")

    return _print


def _parse_screen(s: str) -> tuple:
    m = re.fullmatch(r"(\d+)[xX](\d+)", s)
    if not m:
        raise argparse.ArgumentTypeError(f"--screen 需要 WxH 形式，得到 {s!r}")
    w, h = int(m.group(1)), int(m.group(2))
    if w < 1 or h < 1:
        raise argparse.ArgumentTypeError("--screen 必须为正数")
    return (w, h)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="qrtrans",
        description="把文本文件/目录编码为 QR 码（含阵列），并从 QR 图像还原。",
    )
    sub = p.add_subparsers(dest="command", required=True)

    enc = sub.add_parser("encode", help="把文本文件/目录编码为 QR（含阵列）")
    enc.add_argument("input", type=Path)
    enc.add_argument("-o", "--outdir", type=Path, required=True)
    enc.add_argument("--mode", choices=["colormatrix", "array", "single"],
                     default="colormatrix")
    enc.add_argument("--screen", type=_parse_screen, default=(1920, 1080),
                     metavar="WxH", help="目标屏幕尺寸，默认 1920x1080（仅 array）")
    enc.add_argument("--module-px", type=int, default=3, help="每模块像素，默认 3")
    enc.add_argument("--grid", default="4x2", metavar="WxH",
                     help="QR 阵列网格 WxH（列x行，如 4x2）或 auto；仅 QR array")
    enc.add_argument("--ec", choices=["L", "M", "Q", "H"], default="M")
    enc.add_argument("--chunk-raw-bytes", type=int, default=1300)
    enc.add_argument("--colors", type=int, default=16, choices=[4, 8, 16, 32, 64])
    enc.add_argument("--cell-px", type=int, default=4)
    enc.add_argument("--cm-ecc", type=int, default=12)
    cmcomp = enc.add_mutually_exclusive_group()
    cmcomp.add_argument("--compress", dest="compress", action="store_true", default=True)
    cmcomp.add_argument("--no-compress", dest="compress", action="store_false")
    label = enc.add_mutually_exclusive_group()
    label.add_argument("--label", dest="label", action="store_true", default=True,
                       help="阵列图顶加帧标签横幅（默认）")
    label.add_argument("--no-label", dest="label", action="store_false",
                       help="不加帧标签横幅")
    enc.add_argument("--batch", default="", help="批次 ID（8 位十六进制），不指定则自动生成")

    dec = sub.add_parser("decode", help="从 QR 图像/目录还原文本/目录")
    dec.add_argument("input", type=Path)
    dec.add_argument("-o", "--output", type=Path, required=True)
    dec.add_argument("--strict", action="store_true",
                     help="任一块缺失/校验失败即失败（默认尽力恢复其余）")

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Windows 控制台默认编码（cp1252 等）无法打印 CJK，会让 argparse --help/print 崩溃。
    # 统一切到 UTF-8（errors='replace' 保证绝不抛 UnicodeEncodeError）。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "encode":
        pp = _make_progress_printer()
        try:
            if args.mode == "colormatrix":
                from .cm_encoder import colormatrix_encode, CmEncodeOptions
                opts = CmEncodeOptions(colors=args.colors, cell_px=args.cell_px,
                                       ecc_percent=args.cm_ecc, compress=args.compress,
                                       screen=args.screen, batch=args.batch, label=args.label)
                res = colormatrix_encode(args.input, args.outdir, opts, progress=pp)
                print(f"encoded batch={res.batch} frames={res.frame_count} -> {args.outdir}")
            else:
                opts = EncodeOptions(mode=args.mode, screen=args.screen, module_px=args.module_px,
                                     grid=args.grid, ec=args.ec, chunk_raw_bytes=args.chunk_raw_bytes,
                                     label=args.label, batch=args.batch)
                res = encode(args.input, args.outdir, opts, progress=pp)
                print(f"encoded batch={res.batch} payloads={res.payload_count} files={len(res.output_files)} -> {args.outdir}")
        except (FsError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return _EXIT_FAIL
        return _EXIT_OK

    if args.command == "decode":
        pp = _make_progress_printer()
        try:
            from PIL import Image
            from .cm_decoder import is_colormatrix_frame, colormatrix_decode
            from . import fs_walk
            imgs = fs_walk.gather_images(args.input)
            use_cm = bool(imgs) and is_colormatrix_frame(Image.open(imgs[0]).convert("RGB"))
            if use_cm:
                colormatrix_decode(args.input, args.output, progress=pp)
            else:
                res = decode(args.input, args.output, DecodeOptions(strict=args.strict), progress=pp)
                for w in res.warnings:
                    print(f"warning: {w}", file=sys.stderr)
                for f in res.files_written:
                    print(f"file: {f}")
                for d in res.dirs_created:
                    print(f"dir:  {d}")
                if res.failed:
                    return _EXIT_PARTIAL
        except (DecodeError, FsError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return _EXIT_FAIL
        return _EXIT_OK

    parser.error("unknown command")
    return _EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
