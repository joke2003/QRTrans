from pathlib import Path
import pytest
from qrtrans.fs_walk import collect, rebuild, gather_images, FileRecord, DirRecord, FsError

def test_collect_single_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hi", encoding="utf-8")
    files, dirs = collect(f)
    assert dirs == []
    assert len(files) == 1
    assert files[0].relpath == "a.txt"
    assert files[0].content == "hi".encode("utf-8")

def test_collect_directory_with_nested_and_empty(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("B", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    (tmp_path / "top.txt").write_text("T", encoding="utf-8")
    files, dirs = collect(tmp_path)
    relpaths_f = sorted(f.relpath for f in files)
    relpaths_d = sorted(d.relpath for d in dirs)
    assert relpaths_f == ["sub/b.txt", "top.txt"]
    assert relpaths_d == ["empty/"]
    by_path = {f.relpath: f.content for f in files}
    assert by_path["sub/b.txt"] == b"B"

def test_collect_unicode_filenames(tmp_path):
    (tmp_path / "中文.txt").write_text("内容", encoding="utf-8")
    files, dirs = collect(tmp_path)
    assert files[0].relpath == "中文.txt"
    assert files[0].content == "内容".encode("utf-8")

def test_rebuild_creates_tree(tmp_path):
    out = tmp_path / "out"
    files = [FileRecord("sub/b.txt", b"B"), FileRecord("top.txt", b"T")]
    dirs = [DirRecord("empty/")]
    rebuild(files, dirs, out)
    assert (out / "sub" / "b.txt").read_bytes() == b"B"
    assert (out / "top.txt").read_bytes() == b"T"
    assert (out / "empty").is_dir()

def test_rebuild_rejects_traversal(tmp_path):
    out = tmp_path / "out"
    files = [FileRecord("../escape.txt", b"x")]
    with pytest.raises(FsError):
        rebuild(files, [], out)

def test_rebuild_rejects_absolute(tmp_path):
    out = tmp_path / "out"
    files = [FileRecord("/etc/x", b"x")]
    with pytest.raises(FsError):
        rebuild(files, [], out)

def test_gather_images_file_and_dir(tmp_path):
    # 单文件
    f = tmp_path / "a.png"
    f.write_bytes(b"png")
    assert gather_images(f) == [f]
    # 目录：收集 png/jpg/jpeg，忽略其他
    d = tmp_path / "d"
    d.mkdir()
    (d / "x.png").write_bytes(b"1")
    (d / "y.JPG").write_bytes(b"2")
    (d / "z.txt").write_bytes(b"3")
    (d / "sub").mkdir()
    (d / "sub" / "w.jpeg").write_bytes(b"4")
    imgs = gather_images(d)
    names = sorted(p.name for p in imgs)
    assert names == ["w.jpeg", "x.png", "y.JPG"]
