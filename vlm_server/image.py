"""Validate incoming frames and shrink them before sending to the VLM."""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError


class InvalidImageError(ValueError):
    """Raised when the payload is not a decodable image."""


def prepare_image(data: bytes, *, max_side: int) -> bytes:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("image must be PNG or JPEG") from exc
    image = image.convert("RGB")
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()
