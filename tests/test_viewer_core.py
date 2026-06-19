from pathlib import Path
import json
import pytest
from qrtrans_viewer.core import (
    list_images, ViewerState, write_config, read_config, CONFIG_FILENAME,
)


def test_list_images_dir_sorted(tmp_path):
    (tmp_path / "b.png").write_bytes(b"x")
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "c.txt").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    imgs = list_images(tmp_path)
    assert [p.name for p in imgs] == ["a.png", "b.png"]


def test_list_images_single_file(tmp_path):
    f = tmp_path / "one.png"; f.write_bytes(b"x")
    assert list_images(f) == [f]


def test_state_next_prev_clamp():
    s = ViewerState(images=[Path("a"), Path("b"), Path("c")], index=0,
                    playing=False, interval=3.0, loop=False)
    assert s.next() == Path("b")
    assert s.next() == Path("c")
    assert s.next() == Path("c")   # 末尾钳制（非 loop）
    assert s.prev() == Path("b")


def test_state_loop_wraps():
    s = ViewerState(images=[Path("a"), Path("b")], index=1,
                    playing=False, interval=3.0, loop=True)
    assert s.next() == Path("a")   # loop 回首页


def test_state_first_last():
    s = ViewerState(images=[Path("a"), Path("b"), Path("c")], index=1,
                    playing=False, interval=3.0, loop=False)
    assert s.first() == Path("a")
    assert s.last() == Path("c")


def test_bump_interval_lower_bound():
    s = ViewerState(images=[Path("a")], index=0, playing=False, interval=0.3, loop=False)
    assert s.bump_interval(-0.5) == 0.2


def test_advance_only_when_playing():
    s = ViewerState(images=[Path("a"), Path("b")], index=0,
                    playing=False, interval=0.0, loop=False)
    assert s.advance() is None      # 不播放不进
    s.playing = True
    assert s.advance() == Path("b")


def test_advance_loop_at_end():
    s = ViewerState(images=[Path("a"), Path("b")], index=1,
                    playing=True, interval=0.0, loop=True)
    assert s.advance() == Path("a")


def test_advance_no_loop_at_end_stops():
    s = ViewerState(images=[Path("a"), Path("b")], index=1,
                    playing=True, interval=0.0, loop=False)
    assert s.advance() is None      # 末尾停（不回卷、不越界）
    assert s.playing is False       # 自动暂停


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config((1920, 1080))
    assert read_config() == (1920, 1080)
    data = json.loads((tmp_path / CONFIG_FILENAME).read_text())
    assert data["screen"] == [1920, 1080]
    assert "recorded_at" in data


def test_read_config_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert read_config() is None


def test_read_config_bad_json_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / CONFIG_FILENAME).write_text("{not json")
    assert read_config() is None


def test_write_config_readonly_dir_best_effort(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tmp_path.chmod(0o500)
    try:
        write_config((1280, 720))   # 不应抛
    finally:
        tmp_path.chmod(0o700)
