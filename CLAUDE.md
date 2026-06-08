# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py ~/Music   # path to a folder of MP3 files
```

On Linux, install `libportaudio2` if PortAudio fails to load: `sudo apt install libportaudio2`

There is no build step, test suite, or linter configured in this project.

## Architecture

Spectral is a terminal MP3 player built with Textual (TUI), sounddevice (PortAudio), miniaudio (MP3 decode), NumPy (DSP), and mutagen (ID3 tags).

**Data flow:**

```
playlist.py  →  audio.py  →  dsp.py  →  visualizers.py  →  app.py
(track list)    (PCM data)   (FFT)       (Rich renderables)  (Textual UI)
```

**Module responsibilities:**

- `main.py` — CLI arg parsing, instantiates and runs `SpectralApp`
- `app.py` — Textual `App` subclass; owns the split-pane layout (40% playlist / 60% visualizer), a 30 FPS refresh timer, key bindings, and the status/controls bars
- `audio.py` — `AudioEngine`: decodes the entire MP3 to memory as float32 PCM on load, drives playback via a PortAudio callback (the authoritative position clock), exposes `get_window(n)` for DSP consumers
- `dsp.py` — `compute_spectrum()`: Hann window → rfft → N log-spaced bands (40 Hz–16 kHz) → log-amplitude → normalized [0,1]; `smooth()`: asymmetric easing (fast attack 0.6, slow decay 0.15)
- `visualizers.py` — three render functions returning Rich `Text` renderables: Spectrum (block glyphs ▁–█ per frequency bar), Oscilloscope (time-domain waveform), VU Meter (L/R amplitude with peak-hold)
- `themes.py` — three frozen dataclass palettes (Synthwave, Matrix, Amber CRT) + `interpolate_gradient()` for multi-stop color mapping
- `playlist.py` — `Playlist` class: directory scan, mutagen tag reads, track navigation; separates `cursor` (UI selection) from `index` (now-playing)

**Key design constraints:**

- The PortAudio callback is the single source of truth for playback position. The visualizer pulls a sample window offset 1024 frames behind `position_frames` to match audible output.
- The entire MP3 is decoded to memory upfront — no streaming decode.
- No system-level audio dependencies beyond PortAudio (bundled in the sounddevice wheel on macOS/Windows; `libportaudio2` package on Linux). No ffmpeg required.
