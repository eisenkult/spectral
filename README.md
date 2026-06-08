# Spectral

A minimalist terminal MP3 player with a real-time audio visualizer. Split-pane TUI: scrollable playlist on top, visualizer on the bottom. Three themes, four visualizer modes, all keyboard-driven.

<img width="1246" height="696" alt="image" src="https://github.com/user-attachments/assets/95ed6253-a362-4e97-b599-80a9c9ed3392" />

## Requirements

- Python 3.11+
- A truecolor terminal (recommended): iTerm2, Windows Terminal, GNOME Terminal, Kitty
- **Linux only:** if PortAudio fails to load, install it: `sudo apt install libportaudio2`

## Install & Run

```bash
# 1. Create an isolated environment
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run, pointing at a folder of MP3s
python main.py ~/Music
```
## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/eisenkult/spectral/main/setup.sh | bash
```

## Controls

| Key | Action |
|---|---|
| `↑` / `↓` or `k` / `j` | Move playlist selection |
| `Enter` | Play selected track |
| `Space` | Play / pause |
| `n` / `p` | Next / previous track |
| `o` | Open folder/.m3u |
| `←` / `→` | Seek −5s / +5s |
| `+` / `-` | Volume up / down |
| `v` | Cycle visualizer mode |
| `t` | Cycle theme |
| `q` | Quit |

## Visualizer Modes

- **Spectrum** — frequency domain bars with sub-row block glyph resolution
- **Oscilloscope** — raw waveform plotted left to right
- **VU Meter** — per-channel L/R amplitude with peak redline
- **Matrix** — the video translators work for the construct program

## Themes

- **Synthwave** — deep purple background, magenta-to-cyan gradient
- **Matrix** — black background, green-on-green
- **Amber CRT** — dark amber background, warm gold gradient

## Project Layout

```
spectral/
├── main.py        # entry point: argument parsing + launch
├── app.py         # Textual App: layout, key bindings, panes
├── audio.py       # AudioEngine: decode, playback, position clock, sample window
├── dsp.py         # FFT pipeline: windowing, log-band mapping, smoothing
├── visualizers.py # three render modes
├── themes.py      # three palettes + gradient interpolation
├── playlist.py    # track list, directory scan, mutagen tag reads
└── requirements.txt
```

## Platform Notes

- **Windows:** run inside Windows Terminal for reliable truecolor and Unicode block glyphs.
- **macOS:** PortAudio is bundled in the `sounddevice` wheel — no extra installs needed.
- **Linux:** wheels usually suffice; install `libportaudio2` if the player fails to start.
