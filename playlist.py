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
    index: int = 0   # currently playing track
    cursor: int = 0  # UI selection / navigation position

    def scan(self, folder: str) -> None:
        folder_path = Path(folder)
        mp3_files = sorted(folder_path.glob("*.mp3"))
        self.tracks = []
        for path in mp3_files:
            title, artist, duration = _read_tags(str(path))
            self.tracks.append(Track(str(path), title, artist, duration))
        self.index = 0
        self.cursor = 0

    def load_m3u(self, path: str) -> None:
        m3u_path = Path(path)
        base_dir = m3u_path.parent
        tracks = []
        pending_meta: tuple[str, str, float] | None = None
        try:
            with open(m3u_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if "://" in line:
                        pending_meta = None
                        continue
                    if line.startswith("#EXTINF:"):
                        _, rest = line.split(":", 1)
                        if "," in rest:
                            dur_str, label = rest.split(",", 1)
                            try:
                                dur = float(dur_str)
                            except ValueError:
                                dur = 0.0
                            if " - " in label:
                                artist, title = label.split(" - ", 1)
                            else:
                                artist, title = "", label
                            pending_meta = (title.strip(), artist.strip(), dur)
                    elif not line.startswith("#"):
                        p = Path(line)
                        if not p.is_absolute():
                            p = base_dir / p
                        if p.exists() and p.suffix.lower() == ".mp3":
                            if pending_meta:
                                title, artist, duration = pending_meta
                            else:
                                title, artist, duration = _read_tags(str(p))
                            tracks.append(Track(str(p), title, artist, duration))
                        pending_meta = None
        except OSError:
            pass
        self.tracks = tracks
        self.index = 0
        self.cursor = 0

    def current(self) -> Track | None:
        if not self.tracks:
            return None
        return self.tracks[self.index]

    def next(self) -> Track | None:
        if not self.tracks:
            return None
        self.index = (self.index + 1) % len(self.tracks)
        self.cursor = self.index
        return self.current()

    def prev(self) -> Track | None:
        if not self.tracks:
            return None
        self.index = (self.index - 1) % len(self.tracks)
        self.cursor = self.index
        return self.current()

    def select(self, i: int) -> None:
        if self.tracks and 0 <= i < len(self.tracks):
            self.cursor = i

    def play_cursor(self) -> None:
        self.index = self.cursor


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
