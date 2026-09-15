"""Raster input validation produces actionable errors, not Pillow internals.

Feeding an SVG to raster mode is the natural mistake in this app - everything
else is SVG-driven - and Pillow's own failure for that case is
"cannot identify image file <_io.BytesIO object at 0x...>", which tells a user
nothing. These tests pin the messages that replaced it.
"""
import base64
import io
from pathlib import Path

import pytest

import gcode_service as gs

FIXTURES_DIR = Path(__file__).parent / "fixtures"

pytest.importorskip("PIL", reason="raster validation needs Pillow")
from PIL import Image  # noqa: E402


def data_url(raw: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def png_bytes(w=8, h=6) -> bytes:
    buf = io.BytesIO()
    Image.new("L", (w, h), 255).save(buf, format="PNG")
    return buf.getvalue()


SVG_BYTES = (FIXTURES_DIR / "simple_square.svg").read_bytes()


def test_svg_declared_as_svg_is_rejected_with_guidance():
    with pytest.raises(ValueError) as exc:
        gs._decode_image_data(data_url(SVG_BYTES, "image/svg+xml"))
    msg = str(exc.value)
    assert "SVG" in msg
    assert "Vector mode" in msg, "error should point at the mode that cuts an SVG"
    assert "raster page" in msg, "error should say the raster page rasterises SVG for you"


def test_svg_mislabelled_is_still_detected_by_content():
    """A picker or drag-drop can hand over a wrong or missing MIME type."""
    with pytest.raises(ValueError) as exc:
        gs._decode_image_data(data_url(SVG_BYTES, "application/octet-stream"))
    assert "SVG" in str(exc.value)


def test_svg_with_xml_declaration_is_detected():
    raw = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    with pytest.raises(ValueError) as exc:
        gs._decode_image_data(data_url(raw, "application/octet-stream"))
    assert "SVG" in str(exc.value)


def test_unreadable_bytes_name_the_supported_formats():
    with pytest.raises(ValueError) as exc:
        gs._decode_image_data(data_url(b"not an image at all"))
    msg = str(exc.value)
    assert "PNG" in msg and "JPEG" in msg
    assert "BytesIO" not in msg, "must not leak Pillow's internal repr"


def test_empty_payload():
    with pytest.raises(ValueError, match="empty"):
        gs._decode_image_data("data:image/png;base64,")


def test_missing_payload():
    with pytest.raises(ValueError, match="required"):
        gs._decode_image_data("")


def test_invalid_base64():
    with pytest.raises(ValueError, match="base64"):
        gs._decode_image_data("data:image/png;base64,!!!not-base64!!!")


def test_valid_png_still_decodes():
    """The guards must not block the normal path."""
    img = gs._decode_image_data(data_url(png_bytes()))
    assert img.size == (8, 6)


def test_raw_base64_without_data_url_still_works():
    """The decoder documents support for a bare base64 string."""
    img = gs._decode_image_data(base64.b64encode(png_bytes()).decode())
    assert img.size == (8, 6)
