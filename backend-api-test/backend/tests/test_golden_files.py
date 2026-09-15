"""
Golden-file tests: generate G-code from small fixture SVGs and compare
against committed expected output.

Thumbnail bitmap generation is monkeypatched to a fixed 1x1 blank thumbnail
for these tests: the scan-converted bitmap is unrelated to the correctness
bugs these fixtures exercise (path parsing, transforms) and would otherwise
make golden files large and noisy (a square shape alone produces a ~159-row
thumbnail at the real default resolution).
"""
from pathlib import Path

import pytest

import gcode_service as gs

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def tiny_thumbnail(monkeypatch):
    monkeypatch.setattr(
        gs, "_make_thumbnail_rows", lambda segments, bounds, max_w=1, max_h=1: (1, 1, ["FF"])
    )


CASES = [
    (
        "simple_square.svg",
        [{"color": "#ff0000", "enabled": True, "speed": 1000, "power": 50, "passes": 1}],
        "expected_simple_square.gco",
    ),
    (
        "group_transform.svg",
        [{"color": "#0000ff", "enabled": True, "speed": 1000, "power": 60, "passes": 1}],
        "expected_group_transform.gco",
    ),
    (
        "curves_sqt.svg",
        [{"color": "#00ff00", "enabled": True, "speed": 800, "power": 40, "passes": 1}],
        "expected_curves_sqt.gco",
    ),
]


@pytest.mark.parametrize("svg_name,jobs,expected_name", CASES)
def test_golden_output_matches(svg_name, jobs, expected_name):
    svg_path = FIXTURES_DIR / svg_name
    expected_path = FIXTURES_DIR / expected_name

    actual = gs.generate_vector_gcode_advanced(str(svg_path), jobs, origin="bottom-left")
    expected = expected_path.read_text()

    assert actual == expected


@pytest.mark.parametrize("svg_name,jobs,_expected_name", CASES)
def test_golden_output_fits_bed(svg_name, jobs, _expected_name):
    svg_path = FIXTURES_DIR / svg_name
    gcode = gs.generate_vector_gcode_advanced(str(svg_path), jobs, origin="bottom-left")

    for line in gcode.splitlines():
        line = line.strip()
        if not (line.startswith("G0") or line.startswith("G1")):
            continue
        x = y = None
        for tok in line.split():
            if tok.startswith("X"):
                x = float(tok[1:])
            elif tok.startswith("Y"):
                y = float(tok[1:])
        if x is not None:
            assert -1e-6 <= x <= gs.BED_W_MM + 1e-6, f"X out of bed range: {line}"
        if y is not None:
            assert -1e-6 <= y <= gs.BED_H_MM + 1e-6, f"Y out of bed range: {line}"
