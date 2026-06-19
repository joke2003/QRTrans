from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
CONFIG_FILENAME = "qrtrans.json"
MIN_INTERVAL = 0.2


def list_images(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    return sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


@dataclass
class ViewerState:
    images: List[Path]
    index: int = 0
    playing: bool = False
    interval: float = 3.0
    loop: bool = False

    def _cur(self) -> Optional[Path]:
        if 0 <= self.index < len(self.images):
            return self.images[self.index]
        return None

    def first(self) -> Optional[Path]:
        self.index = 0
        return self._cur()

    def last(self) -> Optional[Path]:
        self.index = max(0, len(self.images) - 1)
        return self._cur()

    def next(self) -> Optional[Path]:
        if not self.images:
            return None
        if self.index < len(self.images) - 1:
            self.index += 1
        elif self.loop:
            self.index = 0
        return self._cur()

    def prev(self) -> Optional[Path]:
        if not self.images:
            return None
        if self.index > 0:
            self.index -= 1
        elif self.loop:
            self.index = len(self.images) - 1
        return self._cur()

    def bump_interval(self, delta: float) -> float:
        self.interval = max(MIN_INTERVAL, self.interval + delta)
        return self.interval

    def advance(self) -> Optional[Path]:
        """自动切换一步：仅当 playing。末尾非 loop → 停止并暂停；loop → 回首页。"""
        if not self.playing or not self.images:
            return None
        if self.index < len(self.images) - 1:
            self.index += 1
            return self._cur()
        if self.loop:
            self.index = 0
            return self._cur()
        self.playing = False
        return None


def write_config(screen: Tuple[int, int], path: str = CONFIG_FILENAME) -> None:
    """best-effort：写失败静默忽略。"""
    data = {"screen": [int(screen[0]), int(screen[1])],
            "recorded_at": datetime.now(timezone.utc).isoformat()}
    try:
        Path(path).write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def read_config(path: str = CONFIG_FILENAME) -> Optional[Tuple[int, int]]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
        w, h = int(data["screen"][0]), int(data["screen"][1])
        if w <= 0 or h <= 0:
            return None
        return (w, h)
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None
