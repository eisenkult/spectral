# Spectral — Terminal MP3 Player + Visualizer
### Design Specification (Proof of Concept)

> Working title: **Spectral**. A minimalist, cross-platform terminal music player with a split-pane UI: scrollable playlist on the left, real-time audio visualizer on the right. Three swappable themes, three visualizer modes. Built to be runnable from a clean machine with one `pip install`.

---

## 1. Goals & Non-Goals

**Goals**
- Single, small Python package that runs cross-platform (Windows / macOS / Linux) with no system-level audio tooling required (no ffmpeg dependency).
- Split-screen TUI: playlist (left) + visualizer (right), driven by keyboard.
- 3 visual themes, 3 visualizer modes, both hot-swappable at runtime.
- Real-time FFT visualization synced to playback.
- "Everything included": pinned dependency list, entry point, run instructions, project layout.

**Non-Goals** (explicitly out of scope for the PoC)
- Library management, tagging, playlists-as-files, gapless/crossfade playback.
- Streaming, network sources, or formats beyond MP3 (the engine can decode others, but only MP3 is in scope).
- Plugin architecture / extensibility hooks / test suite / packaging to PyPI.

---

## 2. Technology Stack

| Concern | Choice | Why |
|---|---|---|
| TUI framework | **Textual** (built on Rich) | Clean layout primitives (horizontal split), native cross-platform keyboard handling incl. Windows, truecolor + automatic 256-color fallback, timer-driven widget refresh. |
| Numerics / FFT | **NumPy** | `rfft`, windowing, band mapping — fast enough that DSP is never the bottleneck. |
| Audio decode | **miniaudio** | Decodes MP3 (and WAV/FLAC/OGG) via a bundled C lib. **No ffmpeg / no libsndfile MP3 quirks.** Ships wheels for all three platforms. |
| Audio playback | **sounddevice** (PortAudio) | Callback-based output stream gives a precise, frame-accurate playback position to sync the visualizer against. PortAudio is bundled in the wheel. |
| Metadata | **mutagen** | Pure-Python ID3 read for track titles / duration in the playlist. |

> Version pinning: install, confirm it runs, then `pip freeze > requirements.txt` to lock. The manifest below uses minimums; lock exact versions for reproducibility.

```
# requirements.txt (minimums — pin exact after first successful run)
textual>=0.60
numpy>=1.26
sounddevice>=0.4.6
miniaudio>=1.59
mutagen>=1.47
```

---

## 3. Project Layout

```
spectral/
├── main.py          # entry point: arg parse + launch
├── app.py           # Textual App: layout, key bindings, the two panes
├── audio.py         # AudioEngine: decode + playback + position + sample window
├── dsp.py           # FFT pipeline + smoothing/decay
├── visualizers.py   # 3 render modes (spectrum / scope / VU)
├── themes.py        # 3 palettes + active-theme state
├── playlist.py      # track list, directory scan, metadata, navigation
├── requirements.txt
└── README.md
```

Six small modules. Each visualizer mode and each theme is a few dozen lines; nothing here should exceed a couple hundred lines.

---

## 4. Architecture & Data Flow

```
            ┌──────────────┐      decode       ┌────────────────────────┐
  MP3 file →│  miniaudio   │ ────────────────► │ samples: float32        │
            └──────────────┘   [frames, ch]    │ [N, channels], rate Hz │
                                               └───────────┬────────────┘
                                                           │
                            sounddevice OutputStream       │ get_window(n)
                            callback copies a chunk and    │ (mono mix, n samples
                            advances `position_frames`     │  near current position)
                                   │                       ▼
                                   │              ┌──────────────────┐
                            (audio out) ◄─────────│      dsp.py      │  Hann → rfft →
                                                  │  compute_spectrum│  log-band → log-amp
                                                  └────────┬─────────┘  → normalize → smooth
                                                           │ frame: ndarray (0..1)
                                                           ▼
                                                  ┌──────────────────┐
                                   theme palette →│  visualizers.py  │→ Rich renderable
                                                  └────────┬─────────┘
                                                           ▼
                                              Textual VisualizerPane.render()
                                              (refreshed on a 30 FPS timer)
```

**Sync model.** The `sounddevice` output callback is the single source of truth for playback position. It copies the next chunk of `samples` to the output buffer and increments `position_frames`. The visualizer pulls a window of samples *at* (or slightly behind, to match buffer latency) `position_frames` each frame, so the bars track what's actually audible. No separate clock to drift.

---

## 5. Module Specs

### 5.1 `audio.py` — AudioEngine
```python
class AudioEngine:
    samples: np.ndarray      # float32, shape [frames, channels], range ~[-1, 1]
    sample_rate: int
    position_frames: int     # advanced by the output callback (authoritative clock)
    volume: float            # 0.0 .. 1.0, applied in the callback

    def load(path: str) -> None      # miniaudio decode_file → float32 ndarray + rate
    def play()  -> None              # start/resume the OutputStream
    def pause() -> None
    def toggle()-> None
    def stop()  -> None
    def seek(seconds: float) -> None # clamp + set position_frames
    def set_volume(delta: float) -> None

    @property
    def duration(self) -> float      # len(samples) / sample_rate
    @property
    def elapsed(self) -> float       # position_frames / sample_rate
    @property
    def finished(self) -> bool       # position_frames >= len(samples)

    def get_window(self, n: int) -> np.ndarray
        # returns n mono samples (mean of channels) starting at position_frames,
        # zero-padded at end-of-track. This is the visualizer's input.
```
- Decode the whole file to memory up front (PoC tracks are minutes long → trivial RAM).
- The output callback is the only place `position_frames` mutates; the UI thread only reads it.
- On `finished`, the app advances to the next track (see playlist).

### 5.2 `dsp.py` — analysis pipeline
```python
def compute_spectrum(window: np.ndarray, n_bars: int, sample_rate: int) -> np.ndarray:
    # 1. Apply a Hann window (reduce spectral leakage)
    # 2. rfft → magnitude spectrum
    # 3. Group linear FFT bins into n_bars LOG-spaced frequency bands
    #    (e.g. 40 Hz .. ~16 kHz) so the display is perceptually even
    # 4. Log-amplitude scaling (dB-ish), normalize to 0..1
    # returns ndarray[n_bars] in 0..1

def smooth(prev: np.ndarray, current: np.ndarray,
           attack: float = 0.6, decay: float = 0.15) -> np.ndarray:
    # asymmetric easing: rise fast (attack), fall slow (decay) → "gravity" on bars
```
- `n_bars` is derived from the visualizer pane width at render time.
- Recommended FFT window length: 2048 samples. Cheap on NumPy.

### 5.3 `visualizers.py` — render modes
Each mode is a callable `render(frame, width, height, theme) -> rich renderable`. Mode cycling is just an index into a list.

1. **Spectrum** *(frequency domain)* — vertical bars across the pane. Sub-row resolution via block glyphs `▁▂▃▄▅▆▇█`; each column colored by height using the theme's gradient.
2. **Oscilloscope** *(time domain)* — the raw mono waveform plotted left→right. Use block columns for the PoC; Braille glyphs (`⠀`–`⣿`, 2×4 dots/cell) are an optional upgrade for a smooth line.
3. **VU Meter** *(amplitude)* — per-channel L/R level bars with peak-hold markers and a redline near clipping. Visually distinct from the spectrum bars.

> Optional 4th (stretch, not required): mirrored/center-out spectrum or a bass-reactive particle bloom — same `render()` signature, drop it in the list.

### 5.4 `themes.py` — palettes
A theme = background, foreground, accent (UI chrome / selection), and a 2–3 stop **gradient** used to color the visualizer by intensity.

| Theme | bg | fg | accent | gradient (low → high) |
|---|---|---|---|---|
| **Synthwave** | `#1a1025` | `#f8f8f2` | `#ff2e97` | `#5a2a82` → `#ff2e97` → `#00e5ff` |
| **Matrix** | `#000000` | `#00ff41` | `#00ff41` | `#005f0a` → `#00ff41` |
| **Amber CRT** | `#1a0f00` | `#ffb000` | `#ff7b00` | `#7a3b00` → `#ffb000` → `#fff3c0` |

- Themes apply to: pane borders/titles, playlist selection highlight, now-playing line, and the visualizer gradient.
- Rich downsamples truecolor to 256-color automatically on limited terminals.

### 5.5 `playlist.py` — track list
```python
class Track:  path: str; title: str; artist: str; duration: float
class Playlist:
    tracks: list[Track]; index: int
    def scan(folder: str) -> None     # glob *.mp3, read tags via mutagen
    def current() -> Track
    def next() / prev() / select(i)
```

### 5.6 `app.py` — Textual App
- Layout: a `Horizontal` container splitting the screen ~40% playlist / ~60% visualizer (configurable). Each pane is a bordered, titled widget.
- `PlaylistPane`: a scrollable list; current selection highlighted in the accent color; now-playing row marked.
- `VisualizerPane`: custom widget whose `render()` calls the active visualizer; refreshed via `set_interval(1/30)` (≈30 FPS). On each tick it pulls `engine.get_window(2048)`, runs `compute_spectrum` + `smooth`, and re-renders.
- A thin status/footer line: track title, `elapsed / duration`, volume, active mode + theme names.

---

## 6. Controls

| Key | Action |
|---|---|
| `↑` / `↓` or `k` / `j` | Move playlist selection |
| `Enter` | Play selected track |
| `Space` | Play / pause |
| `n` / `p` | Next / previous track |
| `←` / `→` | Seek −5s / +5s |
| `+` / `-` | Volume up / down |
| `v` | Cycle visualizer mode |
| `t` | Cycle theme |
| `q` | Quit |

---

## 7. Running It

```bash
# 1. Create an isolated environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run, pointing at a folder of MP3s
python main.py ~/Music            # Windows: python main.py "C:\Users\you\Music"
```

`main.py` takes one positional arg (a folder); it scans for `*.mp3`, builds the playlist, and launches the app.

**Cross-platform notes**
- **Windows:** run inside **Windows Terminal** for truecolor + reliable Unicode block/Braille glyphs (the legacy `conhost` console is weaker). `sounddevice` and `miniaudio` ship Windows wheels — no extra installs.
- **macOS:** PortAudio is bundled in the `sounddevice` wheel; output-only, so no mic permission prompt.
- **Linux:** wheels usually suffice; if PortAudio fails to load, install the system lib (`sudo apt install libportaudio2`).
- A truecolor terminal is recommended; themes degrade gracefully to 256-color via Rich.

---

## 8. Build Order (suggested PoC milestones)

1. **Audio core** — `audio.py`: load an MP3, play/pause, expose `position_frames` + `get_window()`. Verify against wall clock.
2. **Shell** — `app.py` + `playlist.py`: split layout, scan a folder, navigate, play on `Enter`, auto-advance on track end.
3. **First visualizer** — `dsp.py` + spectrum mode wired to the 30 FPS refresh.
4. **Remaining modes** — oscilloscope + VU, plus `v` cycling.
5. **Themes** — `themes.py` + `t` cycling, applied to chrome and gradient.
6. **Polish** — volume, seek, metadata in the status line, README.

---

## 9. Risks / Watch-Items

- **Buffer latency vs. visual sync:** read the window slightly behind `position_frames` (by the output buffer size) so bars match what's heard. Tune the offset by ear.
- **Pane resize:** recompute `n_bars` from the live pane width each frame so the visualizer reflows cleanly.
- **Glyph support:** Braille oscilloscope looks best but needs a capable font; keep the block-glyph version as the default and Braille as an optional flag.
- **Decode time on first play:** whole-file decode is instant for typical tracks; if a very long file stutters on load, decode in a worker thread and show a brief "loading" state.
