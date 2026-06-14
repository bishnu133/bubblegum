"""
bubblegum/core/visual_image.py
==============================
PNG decode/encode boundary for visual regression (V1).

The only part of the visual feature that needs an image codec. Pillow is an
optional dependency (``bubblegum-ai[visual]``); everything else in the visual
path is pure stdlib in ``bubblegum.core.visual``. Callers should check
:func:`pillow_available` and surface a clear install hint when it is missing.
"""

from __future__ import annotations

from pathlib import Path


def pillow_available() -> bool:
    """True when Pillow can be imported."""
    try:
        import PIL  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


PILLOW_HINT = (
    "Visual regression needs Pillow. Install it with: "
    'pip install "bubblegum-ai[visual]"'
)


def load_png_rgba(data: bytes) -> tuple[bytes, int, int]:
    """Decode PNG bytes into ``(rgba_bytes, width, height)`` (RGBA, 8-bit)."""
    from PIL import Image
    import io

    with Image.open(io.BytesIO(data)) as img:
        rgba = img.convert("RGBA")
        return rgba.tobytes(), rgba.width, rgba.height


def save_png(rgba: bytes, width: int, height: int, path: str | Path) -> Path:
    """Encode an RGBA buffer to a PNG file and return its path."""
    from PIL import Image

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img = Image.frombytes("RGBA", (width, height), rgba)
    img.save(out, format="PNG")
    return out
