from __future__ import annotations

import string
import sys
from pathlib import Path

import numpy as np
from rich.text import Text
from rich.style import Style
from rich.console import RenderableType
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Footer
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive

from audio import AudioEngine
from dsp import compute_spectrum, smooth
from playlist import Playlist
from themes import THEMES, Theme
import visualizers as vis


def _list_drives() -> list[Path]:
    """Return mounted drive roots on Windows; empty list elsewhere."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        return [
            Path(f"{c}:\\")
            for i, c in enumerate(string.ascii_uppercase)
            if bitmask & (1 << i)
        ]
    except Exception:
        return [Path(f"{c}:\\") for c in string.ascii_uppercase if Path(f"{c}:\\").exists()]


class BrowserScreen(ModalScreen):
    """File/folder browser for opening a folder or .m3u playlist."""

    CSS = """
    BrowserScreen {
        align: center middle;
    }
    #browser {
        width: 70%;
        height: 80%;
        border: solid $primary;
        background: #1a1025;
    }
    #browser_path {
        height: 1;
        padding: 0 1;
        background: #2a2035;
        color: #ccbbff;
    }
    #browser_list {
        height: 1fr;
        padding: 0 1;
    }
    #browser_hint {
        height: 1;
        padding: 0 1;
        background: #2a2035;
        color: #666666;
    }
    """

    def __init__(self, start_dir: str | None = None) -> None:
        super().__init__()
        self._dir = Path(start_dir).resolve() if start_dir else Path.home()
        self._entries: list[Path | None] = []
        self._cursor = 0
        self._showing_drives = False

    def compose(self) -> ComposeResult:
        with Vertical(id="browser"):
            yield Static("", id="browser_path")
            yield Static("", id="browser_list")
            yield Static("", id="browser_hint")

    def render(self) -> RenderableType:
        return ""

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self._entries = self._build_entries()
        self._cursor = 0
        self._update_display()

    def _build_entries(self) -> list[Path | None]:
        if self._showing_drives:
            return _list_drives()
        entries: list[Path | None] = []
        at_root = self._dir.parent == self._dir
        # On Windows show ".." even at drive root so we can reach the drives list
        if not at_root or sys.platform == "win32":
            entries.append(None)  # ".." go-up sentinel
        try:
            items = sorted(
                self._dir.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
            for p in items:
                if p.name.startswith("."):
                    continue
                if p.is_dir() or (p.is_file() and p.suffix.lower() == ".m3u"):
                    entries.append(p)
        except PermissionError:
            pass
        return entries

    def _update_display(self) -> None:
        path_label = " [Drives]" if self._showing_drives else f" {self._dir}"
        self.query_one("#browser_path", Static).update(path_label)

        list_widget = self.query_one("#browser_list", Static)
        h = list_widget.size.height or 20

        text = Text()
        if not self._entries:
            text.append("  (empty)", style=Style(color="#555555"))
        else:
            total = len(self._entries)
            start = max(0, min(self._cursor - h // 2, total - h))
            for i in range(start, min(start + h, total)):
                entry = self._entries[i]
                is_cursor = i == self._cursor
                if entry is None:
                    label, color = "../", "#888888"
                elif self._showing_drives:
                    label, color = str(entry), "#bb99ff"
                elif entry.is_dir():
                    label, color = f"{entry.name}/", "#bb99ff"
                else:
                    label, color = entry.name, "#88ffcc"
                if is_cursor:
                    text.append(
                        f"▶ {label}\n",
                        style=Style(color="#ffffff", bgcolor="#3a2060", bold=True),
                    )
                else:
                    text.append(f"  {label}\n", style=Style(color=color))

        list_widget.update(text)
        hint = (
            "  [↑↓] move  [Enter] open drive  [Esc] cancel"
            if self._showing_drives
            else "  [↑↓] move  [Enter] open  [o] use this folder  [←/Bksp] up  [Esc] cancel"
        )
        self.query_one("#browser_hint", Static).update(hint)

    def _go_up(self) -> None:
        if self._showing_drives:
            return
        at_root = self._dir.parent == self._dir
        if at_root and sys.platform == "win32":
            self._showing_drives = True
            self._refresh()
        elif not at_root:
            self._dir = self._dir.parent
            self._refresh()

    def on_key(self, event) -> None:
        key = event.key
        n = len(self._entries)
        if key in ("up", "k"):
            if self._cursor > 0:
                self._cursor -= 1
                self._update_display()
        elif key in ("down", "j"):
            if self._cursor < n - 1:
                self._cursor += 1
                self._update_display()
        elif key == "enter":
            if not self._entries:
                return
            entry = self._entries[self._cursor]
            if entry is None:
                self._go_up()
            elif self._showing_drives or entry.is_dir():
                self._dir = entry
                self._showing_drives = False
                self._refresh()
            else:
                self.dismiss(("m3u", str(entry)))
        elif key in ("left", "backspace"):
            self._go_up()
        elif key == "o":
            if not self._showing_drives:
                self.dismiss(("folder", str(self._dir)))
        elif key == "escape":
            self.dismiss(None)


class PlaylistPane(Static):
    DEFAULT_CSS = """
    PlaylistPane {
        width: 40%;
        border: solid $primary;
        overflow-y: scroll;
        padding: 0 1;
    }
    """

    def __init__(self, playlist: Playlist, theme: Theme) -> None:
        super().__init__()
        self._playlist = playlist
        self._theme = theme

    def update_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.refresh()

    def render(self) -> RenderableType:
        playlist = self._playlist
        theme = self._theme
        if not playlist.tracks:
            return Text(
                "No tracks loaded — press [o] to open a folder or playlist.",
                style=Style(color=theme.fg),
            )

        text = Text()
        for i, track in enumerate(playlist.tracks):
            is_playing = i == playlist.index
            is_cursor = i == playlist.cursor
            prefix = "▶ " if is_playing else "  "
            line = f"{prefix}{track.title}"
            if track.artist:
                line += f" — {track.artist}"
            duration_str = _fmt_time(track.duration)
            line = line[:50] + f"  {duration_str}"

            if is_cursor:
                style = Style(color=theme.bg, bgcolor=theme.accent, bold=True)
            else:
                style = Style(color=theme.fg)

            text.append(line + "\n", style=style)
        return text


class VisualizerPane(Static):
    DEFAULT_CSS = """
    VisualizerPane {
        width: 60%;
        height: 100%;
        border: solid $primary;
    }
    """

    def __init__(self, engine: AudioEngine, theme: Theme) -> None:
        super().__init__()
        self._engine = engine
        self._theme = theme
        self._mode_index = 0
        self._prev_frame: np.ndarray | None = None

    def update_theme(self, theme: Theme) -> None:
        self._theme = theme

    def cycle_mode(self) -> None:
        self._mode_index = (self._mode_index + 1) % len(vis.MODES)
        self._prev_frame = None
        self.refresh()

    @property
    def mode_name(self) -> str:
        return vis.MODE_NAMES[self._mode_index]

    def on_mount(self) -> None:
        self.set_interval(1 / 30, self._tick)

    def _tick(self) -> None:
        self.refresh()

    def render(self) -> RenderableType:
        engine = self._engine
        theme = self._theme
        w = self.size.width
        h = self.size.height

        if w <= 0 or h <= 0:
            return Text("")

        window = engine.get_window(2048)
        render_fn = vis.MODES[self._mode_index]

        if self._mode_index == 0:
            frame = compute_spectrum(window, n_bars=w, sample_rate=engine.sample_rate)
            frame = smooth(self._prev_frame, frame)
            self._prev_frame = frame
        else:
            frame = window

        return render_fn(frame, w, h, theme)


class ControlsBar(Static):
    DEFAULT_CSS = """
    ControlsBar {
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__("")

    def on_mount(self) -> None:
        t = Text()
        playback = [
            ("p", "prev"),
            ("←/→", "±5s"),
            ("Spc", "play/pause"),
            ("n", "next"),
            ("s", "stop"),
        ]
        for key, label in playback:
            t.append(f"[{key}]", style="bold")
            t.append(f" {label}  ", style="dim")
        t.append("│  ", style="dim")
        for key, label in [("o", "open"), ("t", "theme"), ("v", "viz"), ("+/-", "vol")]:
            t.append(f"[{key}]", style="bold")
            t.append(f" {label}  ", style="dim")
        self.update(t)


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__("")

    def update_status(
        self,
        title: str,
        elapsed: float,
        duration: float,
        volume: float,
        mode: str,
        theme_name: str,
        playing: bool,
    ) -> None:
        state = "▶" if playing else "⏸"
        elapsed_str = _fmt_time(elapsed)
        duration_str = _fmt_time(duration)
        vol_pct = int(volume * 100)
        self.update(
            f"{state} {title}  {elapsed_str}/{duration_str}  Vol:{vol_pct}%  [{mode}]  [{theme_name}]"
        )


class SpectralApp(App):
    CSS = """
    Screen {
        background: #1a1025;
    }
    Horizontal {
        height: 1fr;
    }
    """

    def __init__(self, folder: str | None = None) -> None:
        super().__init__()
        self._folder = folder
        self._engine = AudioEngine()
        self._playlist = Playlist()
        self._theme_index = 0

    @property
    def _theme(self) -> Theme:
        return THEMES[self._theme_index]

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield PlaylistPane(self._playlist, self._theme)
            yield VisualizerPane(self._engine, self._theme)
        yield ControlsBar()
        yield StatusBar()

    def on_mount(self) -> None:
        self.set_interval(0.5, self._poll_status)
        self.set_interval(0.1, self._poll_finished)
        if self._folder:
            self._playlist.scan(self._folder)
            self.query_one(PlaylistPane).refresh()
            self._play_current()
        else:
            self.call_after_refresh(
                lambda: self.push_screen(BrowserScreen(), self._on_browser_result)
            )

    def _on_browser_result(self, result) -> None:
        if result is None:
            return
        kind, path = result
        self._engine.stop()
        if kind == "folder":
            self._folder = path
            self._playlist.scan(path)
        else:
            self._playlist.load_m3u(path)
        self.query_one(PlaylistPane).refresh()
        self._play_current()

    def _play_current(self) -> None:
        track = self._playlist.current()
        if track:
            self._engine.load(track.path)
            self._engine.play()
            self.query_one(PlaylistPane).refresh()

    def _poll_finished(self) -> None:
        if self._engine.finished:
            self._playlist.next()
            self._play_current()

    def _poll_status(self) -> None:
        track = self._playlist.current()
        if not track:
            return
        self.query_one(StatusBar).update_status(
            title=track.title,
            elapsed=self._engine.elapsed,
            duration=self._engine.duration,
            volume=self._engine.volume,
            mode=self.query_one(VisualizerPane).mode_name,
            theme_name=self._theme.name,
            playing=self._engine.is_playing,
        )

    def on_key(self, event) -> None:
        key = event.key
        playlist_pane = self.query_one(PlaylistPane)
        viz_pane = self.query_one(VisualizerPane)

        if key in ("up", "k"):
            self._playlist.select(self._playlist.cursor - 1)
            playlist_pane.refresh()
        elif key in ("down", "j"):
            self._playlist.select(self._playlist.cursor + 1)
            playlist_pane.refresh()
        elif key == "enter":
            self._playlist.play_cursor()
            self._play_current()
        elif key == "space":
            self._engine.toggle()
        elif key == "s":
            self._engine.stop()
        elif key == "n":
            self._playlist.next()
            self._play_current()
        elif key == "p":
            self._playlist.prev()
            self._play_current()
        elif key == "left":
            self._engine.seek_relative(-5.0)
        elif key == "right":
            self._engine.seek_relative(5.0)
        elif key == "plus":
            self._engine.set_volume(0.1)
        elif key == "minus":
            self._engine.set_volume(-0.1)
        elif key == "v":
            viz_pane.cycle_mode()
        elif key == "t":
            self._theme_index = (self._theme_index + 1) % len(THEMES)
            theme = self._theme
            self.set_background(theme.bg)
            playlist_pane.update_theme(theme)
            viz_pane.update_theme(theme)
        elif key == "o":
            start = self._folder or str(Path.home())
            self.push_screen(BrowserScreen(start), self._on_browser_result)
        elif key == "q":
            self._engine.stop()
            self.exit()

    def set_background(self, color: str) -> None:
        self.screen.styles.background = color


def _fmt_time(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"
