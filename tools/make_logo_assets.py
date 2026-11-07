"""Derive the dashboard's logo files from the brand originals in DESIGN/logo/.

The originals are navy and blue on a solid white background. The dashboard forbids blue and
white (DESIGN/DASHBOARD_DESIGN.md), so, by the user's decision of 2026-11-07, the served copies
are recoloured to the theme: the white background becomes transparent, the navy car becomes
light (text-primary), the bright blue brackets and plate outline become the accent green and
the lighter blue signal arcs the bright green. The colours are the tokens in
src/tracko_anpr/dashboard/static/theme.css.

Run from the project root:  uv run python tools/make_logo_assets.py
Writes src/tracko_anpr/dashboard/static/logo/{logo-full,mark,favicon}.png. Deterministic.
"""

from __future__ import annotations

import colorsys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "DESIGN" / "logo"
TARGET = ROOT / "src" / "tracko_anpr" / "dashboard" / "static" / "logo"

TEXT_PRIMARY = (0xF5, 0xF5, 0xF5)  # --text-primary: the car body
ACCENT_GREEN = (0x36, 0xD4, 0x28)  # --accent-green: brackets and plate outline (bright blue in the original)
BRIGHT_GREEN = (0x4A, 0xDE, 0x36)  # --accent-green-bright: signal arcs (light blue in the original)


def recolour(image: Image.Image) -> Image.Image:
    """White → transparent (soft at the edges); navy → light; blues → greens by lightness."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    height, width, _ = rgb.shape
    flat = rgb.reshape(-1, 3)
    hsv = np.array([colorsys.rgb_to_hsv(*pixel) for pixel in flat], dtype=np.float32)
    saturation, value = hsv[:, 1], hsv[:, 2]

    # Opacity: how far the pixel is from pure white. Anti-aliased edges keep a soft alpha.
    whiteness = flat.min(axis=1)  # 1.0 for white, lower for anything coloured or dark
    alpha = np.clip((1.0 - whiteness) * 1.15, 0.0, 1.0)
    alpha[saturation < 0.08] = np.clip((1.0 - value[saturation < 0.08]) * 1.15, 0.0, 1.0)  # grays by darkness

    out = np.zeros_like(flat)
    navy = value < 0.45  # the dark car body
    light_blue = (~navy) & (saturation < 0.72)  # the pale signal arcs
    blue = (~navy) & ~light_blue
    out[navy] = np.array(TEXT_PRIMARY) / 255.0
    out[blue] = np.array(ACCENT_GREEN) / 255.0
    out[light_blue] = np.array(BRIGHT_GREEN) / 255.0
    rgba = np.concatenate([out, alpha[:, None]], axis=1).reshape(height, width, 4)
    return Image.fromarray((rgba * 255).round().astype(np.uint8), "RGBA")


def crop_to_content(image: Image.Image, margin: int = 8) -> Image.Image:
    alpha = np.asarray(image)[:, :, 3]
    rows, cols = np.where(alpha > 8)
    top, bottom, left, right = rows.min(), rows.max(), cols.min(), cols.max()
    return image.crop((max(0, left - margin), max(0, top - margin), right + margin + 1, bottom + margin + 1))


def fit(image: Image.Image, width: int | None = None, height: int | None = None) -> Image.Image:
    ratio = image.width / image.height
    if height is not None and width is None:
        width = round(height * ratio)
    if width is not None and height is None:
        height = round(width / ratio)
    return image.resize((width, height), Image.LANCZOS)


def square(image: Image.Image, size: int) -> Image.Image:
    """The image centred on a transparent square canvas."""
    fitted = fit(image, width=size) if image.width >= image.height else fit(image, height=size)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2), fitted)
    return canvas


def report(name: str, image: Image.Image) -> None:
    pixels = np.asarray(image).reshape(-1, 4)
    opaque = pixels[pixels[:, 3] > 128][:, :3].astype(int)
    blue_like = int(((opaque[:, 2] > opaque[:, 1] + 20) & (opaque[:, 2] > opaque[:, 0] + 20)).sum())
    print(f"{name}: {image.width}x{image.height}, {len(opaque):,} opaque pixels, {blue_like} blue-looking pixels")


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    full = crop_to_content(recolour(Image.open(SOURCE / "full.png")))
    mark = crop_to_content(recolour(Image.open(SOURCE / "half.png")))

    outputs = {
        "logo-full.png": fit(full, height=96),
        "mark.png": square(mark, 256),
        "favicon.png": square(mark, 64),
    }
    for name, image in outputs.items():
        image.save(TARGET / name, optimize=True)
        report(name, image)
        print(f"  -> {TARGET / name} ({(TARGET / name).stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
