import os
from dataclasses import dataclass, field
from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1


@dataclass
class Track:
    path: str
    title: str
    artist: str
    duration: float


@dataclass
class Playlist:
    tracks: list[Track] = field(default_factory=list)
    index: int = 0

    def scan(self, folder: str) -> None:
        folder_path = Path(folder)
        mp3_files = sorted(folder_path.glob("*.mp3"))
        self.tracks = []
        for path in mp3_files:
            title, artist, duration = _read_tags(str(path))
            self.tracks.append(Track(str(path), title, artist, duration))
        self.index = 0

    def current(self) -> Track | None:
        if not self.tracks:
            return None
        return self.tracks[self.index]

    def next(self) -> Track | None:
        if not self.tracks:
            return None
        self.index = (self.index + 1) % len(self.tracks)
        return self.current()

    def prev(self) -> Track | None:
        if not self.tracks:
            return None
        self.index = (self.index - 1) % len(self.tracks)
        return self.current()

    def select(self, i: int) -> Track | None:
        if not self.tracks or not (0 <= i < len(self.tracks)):
            return None
        self.index = i
        return self.current()


def _read_tags(path: str) -> tuple[str, str, float]:
    name = Path(path).stem
    title = name
    artist = ""
    duration = 0.0
    try:
        audio = MP3(path)
        duration = audio.info.length
        tags = audio.tags
        if tags:
            title = str(tags.get("TIT2", name) or name)
            artist = str(tags.get("TPE1", "") or "")
    except Exception:
        pass
    return title, artist, duration
