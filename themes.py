from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    fg: str
    accent: str
    gradient: list[str]


THEMES: list[Theme] = [
    Theme(
        name="Synthwave",
        bg="#1a1025",
        fg="#f8f8f2",
        accent="#ff2e97",
        gradient=["#5a2a82", "#ff2e97", "#00e5ff"],
    ),
    Theme(
        name="Matrix",
        bg="#000000",
        fg="#00ff41",
        accent="#00ff41",
        gradient=["#005f0a", "#00ff41"],
    ),
    Theme(
        name="Amber CRT",
        bg="#1a0f00",
        fg="#ffb000",
        accent="#ff7b00",
        gradient=["#7a3b00", "#ffb000", "#fff3c0"],
    ),
]


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def interpolate_gradient(gradient: list[str], t: float) -> str:
    """Map t in [0,1] to an interpolated hex color across gradient stops."""
    if len(gradient) == 1:
        return gradient[0]
    stops = len(gradient) - 1
    scaled = t * stops
    i = min(int(scaled), stops - 1)
    local_t = scaled - i
    r1, g1, b1 = hex_to_rgb(gradient[i])
    r2, g2, b2 = hex_to_rgb(gradient[i + 1])
    r = int(r1 + (r2 - r1) * local_t)
    g = int(g1 + (g2 - g1) * local_t)
    b = int(b1 + (b2 - b1) * local_t)
    return f"#{r:02x}{g:02x}{b:02x}"
