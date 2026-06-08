import random

import numpy as np
from rich.text import Text
from rich.style import Style
from themes import Theme, interpolate_gradient

BLOCK_GLYPHS = " ▁▂▃▄▅▆▇█"
MATRIX_GLYPHS = "ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789"


def render_spectrum(
    frame: np.ndarray, width: int, height: int, theme: Theme
) -> Text:
    """Vertical frequency bars using block glyphs."""
    text = Text()
    n = len(frame)
    if n == 0 or width == 0 or height == 0:
        return text

    lines: list[list[tuple[str, str]]] = [[] for _ in range(height)]

    for col in range(width):
        bar_idx = min(int(col * n / width), n - 1)
        val = float(frame[bar_idx])
        total_eighths = int(val * height * 8)
        color = interpolate_gradient(theme.gradient, val)

        for row in range(height):
            row_eighths = total_eighths - (height - 1 - row) * 8
            if row_eighths <= 0:
                glyph = " "
            elif row_eighths >= 8:
                glyph = "█"
            else:
                glyph = BLOCK_GLYPHS[row_eighths]
            lines[row].append((glyph, color if glyph != " " else theme.bg))

    result = Text()
    for row_idx, row in enumerate(lines):
        for glyph, color in row:
            result.append(glyph, style=Style(color=color, bgcolor=theme.bg))
        if row_idx < height - 1:
            result.append("\n")
    return result


def render_oscilloscope(
    frame: np.ndarray, width: int, height: int, theme: Theme
) -> Text:
    """Raw waveform plotted left to right."""
    result = Text()
    if len(frame) == 0 or width == 0 or height == 0:
        return result

    grid = [[" "] * width for _ in range(height)]

    for col in range(width):
        sample_idx = min(int(col * len(frame) / width), len(frame) - 1)
        val = float(frame[sample_idx])  # -1..1
        # Map to row: val=1.0 → row 0 (top), val=-1.0 → row height-1 (bottom)
        row = int((1.0 - (val + 1.0) / 2.0) * (height - 1))
        row = max(0, min(height - 1, row))
        grid[row][col] = "█"

    for row_idx, row in enumerate(grid):
        for col_idx, glyph in enumerate(row):
            color = theme.accent if glyph != " " else theme.bg
            result.append(glyph, style=Style(color=color, bgcolor=theme.bg))
        if row_idx < height - 1:
            result.append("\n")
    return result


def render_vu(
    frame: np.ndarray, width: int, height: int, theme: Theme
) -> Text:
    """Per-channel L/R VU meter bars with peak-hold and redline."""
    result = Text()
    if len(frame) == 0 or width == 0 or height == 0:
        return result

    # For mono window, duplicate to fake L/R
    half = len(frame) // 2
    left = frame[:half]
    right = frame[half:]

    l_level = float(np.sqrt(np.mean(left ** 2))) if len(left) > 0 else 0.0
    r_level = float(np.sqrt(np.mean(right ** 2))) if len(right) > 0 else 0.0
    # Normalize RMS (typical RMS of 0.1 → full bar at 0.3)
    l_level = min(l_level * 3.0, 1.0)
    r_level = min(r_level * 3.0, 1.0)

    bar_w = max(1, (width - 3) // 2)
    label_col = width // 2

    for row in range(height):
        t = 1.0 - row / height  # 0 at bottom, 1 at top
        redline = t > 0.9

        for ch_level, label in [(l_level, "L"), (r_level, "R")]:
            filled = t <= ch_level
            if redline:
                color = "#ff2222"
            else:
                color = interpolate_gradient(theme.gradient, t)

            for _ in range(bar_w):
                glyph = "█" if filled else " "
                result.append(glyph, style=Style(color=color, bgcolor=theme.bg))

            # Channel label in middle
            if label == "L":
                result.append(" ", style=Style(bgcolor=theme.bg))
                result.append(label if row == height // 2 else " ", style=Style(color=theme.fg, bgcolor=theme.bg))
                result.append(" ", style=Style(bgcolor=theme.bg))

        if row < height - 1:
            result.append("\n")
    return result


class MatrixRain:
    """Falling katakana/digit glyphs, speed modulated by audio energy."""

    def __init__(self) -> None:
        self._width = 0
        self._height = 0
        self._cols: list[dict] = []

    def _make_col(self, height: int, delayed: bool) -> dict:
        trail = random.randint(max(4, height // 5), height)
        speed = random.uniform(0.25, 1.0)
        # Stagger start positions above screen so columns don't all appear at once
        head = float(-random.randint(1, height + trail) if delayed else -trail)
        glyphs = [random.choice(MATRIX_GLYPHS) for _ in range(trail + 1)]
        return {"head": head, "speed": speed, "trail": trail, "glyphs": glyphs}

    def __call__(self, frame: np.ndarray, width: int, height: int, theme: Theme) -> Text:
        if width != self._width or height != self._height:
            self._width = width
            self._height = height
            self._cols = [self._make_col(height, delayed=True) for _ in range(width)]

        # Audio RMS drives speed; silence = slow drift, loud = fast cascade
        energy = 0.0
        if len(frame) > 0:
            energy = float(np.sqrt(np.mean(frame ** 2)))
            energy = min(energy * 4.0, 1.0)
        speed_mult = 0.4 + energy * 1.6

        # Build brightness grid: (glyph, 0..1) per cell
        grid: list[list[tuple[str, float]]] = [[(" ", 0.0)] * width for _ in range(height)]

        for col_idx, c in enumerate(self._cols):
            c["head"] += c["speed"] * speed_mult
            head = int(c["head"])
            trail = c["trail"]
            glyphs = c["glyphs"]

            # Randomly flicker a glyph inside the trail
            if random.random() < 0.15:
                glyphs[random.randrange(len(glyphs))] = random.choice(MATRIX_GLYPHS)

            for offset in range(trail + 1):
                row = head - offset
                if 0 <= row < height:
                    brightness = 1.0 if offset == 0 else 1.0 - offset / trail
                    grid[row][col_idx] = (glyphs[offset % len(glyphs)], brightness)

            if head - trail > height:
                self._cols[col_idx] = self._make_col(height, delayed=False)

        result = Text()
        for row_idx in range(height):
            for col_idx in range(width):
                glyph, brightness = grid[row_idx][col_idx]
                if brightness <= 0.0:
                    result.append(" ", style=Style(bgcolor=theme.bg))
                else:
                    # Head glyph is theme fg (bright white/green); trail fades through gradient
                    color = theme.fg if brightness > 0.95 else interpolate_gradient(theme.gradient, brightness * 0.85)
                    result.append(glyph, style=Style(color=color, bgcolor=theme.bg))
            if row_idx < height - 1:
                result.append("\n")
        return result


_matrix_rain = MatrixRain()

MODES = [render_spectrum, render_oscilloscope, render_vu, _matrix_rain]
MODE_NAMES = ["Spectrum", "Oscilloscope", "VU Meter", "Matrix Rain"]
