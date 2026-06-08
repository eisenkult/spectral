from __future__ import annotations

import numpy as np
from rich.text import Text
from rich.style import Style
from rich.console import RenderableType
from textual.app import App, ComposeResult
from textual.widgets import Static, Footer
from textual.containers import Horizontal
from textual.reactive import reactive

from audio import AudioEngine
from dsp import compute_spectrum, smooth
from playlist import Playlist
from themes import THEMES, Theme
import visualizers as vis


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
            return Text("No MP3 files found.", style=Style(color=theme.fg))

        text = Text()
        for i, track in enumerate(playlist.tracks):
            is_selected = i == playlist.index
            prefix = "▶ " if is_selected else "  "
            line = f"{prefix}{track.title}"
            if track.artist:
                line += f" — {track.artist}"
            duration_str = _fmt_time(track.duration)
            # Pad title to leave room for duration
            line = line[:50] + f"  {duration_str}"

            if is_selected:
                style = Style(color=theme.bg, bgcolor=theme.accent, bold=True)
            else:
                style = Style(color=theme.fg)

            text.append(line + "\n", style=style)
        return text


class VisualizerPane(Static):
    DEFAULT_CSS = """
    VisualizerPane {
        width: 60%;
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
        w = self.size.width - 2  # subtract border
        h = self.size.height - 2

        if w <= 0 or h <= 0:
            return Text("")

        window = engine.get_window(2048)
        render_fn = vis.MODES[self._mode_index]

        if self._mode_index == 0:
            # Spectrum mode: run DSP
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
        dock: bottom;
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
        for key, label in [("t", "theme"), ("v", "viz"), ("+/-", "vol")]:
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

    def __init__(self, folder: str) -> None:
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
        self._playlist.scan(self._folder)
        self.query_one(PlaylistPane).refresh()
        self.set_interval(0.5, self._poll_status)
        self.set_interval(0.1, self._poll_finished)
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
            self._playlist.select(max(0, self._playlist.index - 1))
            playlist_pane.refresh()
        elif key in ("down", "j"):
            self._playlist.select(
                min(len(self._playlist.tracks) - 1, self._playlist.index + 1)
            )
            playlist_pane.refresh()
        elif key == "enter":
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
        elif key == "q":
            self._engine.stop()
            self.exit()

    def set_background(self, color: str) -> None:
        self.screen.styles.background = color


def _fmt_time(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"
