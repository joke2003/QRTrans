from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import List, Tuple

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


class FsError(Exception):
    pass


@dataclass(frozen=True)
class FileRecord:
    relpath: str   # posix 相对路径
    content: bytes


@dataclass(frozen=True)
class DirRecord:
    relpath: str   # 以 "/" 结尾


def _to_relposix(root: Path, abs_path: Path) -> str:
    rel = abs_path.relative_to(root)
    return PurePosixPath(*rel.parts).as_posix()


def collect(input_path: Path) -> Tuple[List[FileRecord], List[DirRecord]]:
    input_path = input_path.resolve()
    if input_path.is_file():
        return [FileRecord(input_path.name, input_path.read_bytes())], []
    if not input_path.is_dir():
        raise FsError(f"not a file or directory: {input_path}")

    files: List[FileRecord] = []
    dirs: List[DirRecord] = []
    for dirpath, dirnames, filenames in os.walk(input_path):
        current = Path(dirpath)
        rel_dir = _to_relposix(input_path, current)
        if not filenames and not dirnames:
            if rel_dir != ".":
                dirs.append(DirRecord(rel_dir + "/"))
        for fn in filenames:
            absf = current / fn
            rel = _to_relposix(input_path, absf)
            files.append(FileRecord(rel, absf.read_bytes()))
    return files, dirs


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def rebuild(files: List[FileRecord], dirs: List[DirRecord], out_root: Path) -> None:
    out_root = out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    for d in dirs:
        rel = d.relpath.rstrip("/")
        if not rel:
            continue
        target = (out_root / rel).resolve()
        if not _is_within(target, out_root):
            raise FsError(f"unsafe dir path: {d.relpath}")
        target.mkdir(parents=True, exist_ok=True)

    for f in files:
        target = (out_root / f.relpath).resolve()
        if not _is_within(target, out_root):
            raise FsError(f"unsafe file path: {f.relpath}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.content)


def gather_images(input_path: Path) -> List[Path]:
    """解码端：收集输入（文件或目录）下所有图像。"""
    input_path = input_path.resolve()
    if input_path.is_file():
        return [input_path]
    if not input_path.is_dir():
        raise FsError(f"not a file or directory: {input_path}")
    imgs: List[Path] = []
    for dirpath, _, filenames in os.walk(input_path):
        for fn in filenames:
            if Path(fn).suffix.lower() in IMAGE_SUFFIXES:
                imgs.append(Path(dirpath) / fn)
    return sorted(imgs)
