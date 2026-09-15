"""Custom origin places the design's bottom-left corner at (origin_x, origin_y).

The implementation used to apply a top-down flip (`BED_H_MM - origin_y - h`) to
coordinates that had already been converted to machine Y-up, which double-
flipped the placement. Custom (0, 0) landed the job at the top of the bed, and
the workspace preview - which measures origin Y up from the bottom - disagreed
with what was actually cut.
"""
import re
from pathlib import Path

import pytest

import gcode_service as gs

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SVG = str(FIXTURES_DIR / "simple_square.svg")
JOBS = [{"color": "#ff0000", "enabled": True, "speed": 1000, "power": 50, "passes": 1}]

# simple_square.svg is a 40x40mm path inside a 50x50mm document.
JOB_SIZE = 40.0
BED_H = 285.0


def cut_bounds(gcode):
    """(min_x, min_y, max_x, max_y) over moves made with the laser on."""
    x = y = 0.0
    laser_on = False
    xs, ys = [], []
    for raw in gcode.splitlines():
        line = raw.split(";")[0].strip()
        if not line:
            continue
        if re.match(r"^M0*5\b", line):
            laser_on = False
        elif re.match(r"^M0*[34]\b", line):
            laser_on = True
        m = re.match(r"^G0*([01])\b", line)
        if not m:
            continue
        xm = re.search(r"\bX(-?\d*\.?\d+)", line)
        ym = re.search(r"\bY(-?\d*\.?\d+)", line)
        nx = float(xm.group(1)) if xm else x
        ny = float(ym.group(1)) if ym else y
        if m.group(1) == "1" and laser_on:
            xs += [x, nx]
            ys += [y, ny]
        x, y = nx, ny
    assert xs, "no cutting moves emitted"
    return min(xs), min(ys), max(xs), max(ys)


def generate(origin, ox=None, oy=None):
    return gs.generate_vector_gcode_advanced(
        svg_path=SVG, jobs=JOBS, origin=origin, origin_x=ox, origin_y=oy
    )


@pytest.mark.parametrize("ox,oy", [(0, 0), (100, 50), (25.5, 12.25), (460, 245)])
def test_custom_origin_places_bottom_left_corner(ox, oy):
    min_x, min_y, max_x, max_y = cut_bounds(generate("custom", ox, oy))
    assert min_x == pytest.approx(ox, abs=0.01)
    assert min_y == pytest.approx(oy, abs=0.01)
    assert max_x == pytest.approx(ox + JOB_SIZE, abs=0.01)
    assert max_y == pytest.approx(oy + JOB_SIZE, abs=0.01)


def test_custom_zero_equals_bottom_left():
    """The invariant the double flip broke: custom (0,0) == bottom-left."""
    assert cut_bounds(generate("custom", 0, 0)) == pytest.approx(
        cut_bounds(generate("bottom-left"))
    )


def test_custom_origin_is_not_top_left():
    """Regression guard: custom (0,0) used to be identical to top-left."""
    assert cut_bounds(generate("custom", 0, 0)) != pytest.approx(
        cut_bounds(generate("top-left"))
    )


def test_presets_are_unaffected():
    """The fix must only touch the custom path."""
    assert cut_bounds(generate("bottom-left")) == pytest.approx((0, 0, 40, 40))
    assert cut_bounds(generate("top-left")) == pytest.approx(
        (0, BED_H - JOB_SIZE, 40, BED_H)
    )


def test_custom_without_coords_falls_back_to_bottom_left():
    assert cut_bounds(generate("custom", None, None)) == pytest.approx(
        cut_bounds(generate("bottom-left"))
    )
