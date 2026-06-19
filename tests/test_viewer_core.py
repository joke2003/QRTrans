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


def test_state_empty_list_safe():
    s = ViewerState(images=[], index=0, playing=True, interval=0.0, loop=True)
    assert s.next() is None
    assert s.prev() is None
    assert s.first() is None
    assert s.last() is None
    assert s.advance() is None


def test_state_prev_clamp_at_start():
    s = ViewerState(images=[Path("a"), Path("b")], index=0,
                    playing=False, interval=3.0, loop=False)
    assert s.prev() == Path("a")   # 首部钳制


def test_state_prev_loop_wraps():
    s = ViewerState(images=[Path("a"), Path("b"), Path("c")], index=0,
                    playing=False, interval=3.0, loop=True)
    assert s.prev() == Path("c")   # loop 首→末回卷


def test_state_index_out_of_range_does_not_raise():
    s = ViewerState(images=[Path("a"), Path("b")], index=99,
                    playing=False, interval=3.0, loop=False)
    assert s._cur() is None        # 加固 1：不抛 IndexError


def test_read_config_missing_screen_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / CONFIG_FILENAME).write_text('{"foo": 1}')
    assert read_config() is None


def test_read_config_non_dict_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / CONFIG_FILENAME).write_text('[1, 2, 3]')
    assert read_config() is None


def test_read_config_non_int_screen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / CONFIG_FILENAME).write_text('{"screen": ["a", "b"]}')
    assert read_config() is None


def test_read_config_screen_too_short(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / CONFIG_FILENAME).write_text('{"screen": [1920]}')
    assert read_config() is None


def test_read_config_non_positive_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / CONFIG_FILENAME).write_text('{"screen": [-1, 0]}')
    assert read_config() is None


def test_list_images_nonexistent_path(tmp_path):
    assert list_images(tmp_path / "nope") == []


def test_list_images_uppercase_suffix(tmp_path):
    (tmp_path / "x.JPG").write_bytes(b"x")
    (tmp_path / "y.PNG").write_bytes(b"x")
    assert [p.name for p in list_images(tmp_path)] == ["x.JPG", "y.PNG"]


def test_write_config_readonly_does_not_create_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tmp_path.chmod(0o500)
    try:
        write_config((1280, 720))   # best-effort，不应抛
    finally:
        tmp_path.chmod(0o700)
    assert not (tmp_path / CONFIG_FILENAME).exists()   # 且不应留下文件
