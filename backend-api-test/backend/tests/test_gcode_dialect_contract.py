"""Pins the G-code dialect that frontend/toolpath-preview.js depends on.

The toolpath preview parses the emitted G-code rather than the source SVG, so
it can show what the machine will actually do. That makes the backend's output
format a real interface between the two. Wintermute has no JS runtime, so the
JS parser cannot be unit-tested here; these tests instead assert the properties
that parser relies on, so a dialect change breaks the build rather than
silently blanking the preview.

If one of these fails, frontend/toolpath-preview.js::parse must be updated too.
"""
import re
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

MOVE_RE = re.compile(r"^(G0|G1)\b")


def _read(name):
    return (FIXTURES_DIR / name).read_text()


@pytest.fixture
def simple_square_gcode():
    """Committed golden output - already pinned by test_golden_files.py."""
    return _read("expected_simple_square.gco")


@pytest.fixture
def curves_gcode():
    return _read("expected_curves_sqt.gco")


def _code_lines(gcode):
    """Program lines with comments and blank lines removed."""
    out = []
    for raw in gcode.splitlines():
        line = raw.split(";")[0].strip()
        if line:
            out.append(line)
    return out


def test_laser_gated_by_m3_m5(simple_square_gcode):
    """Cuts are bracketed by M3/M5, never left implicitly on."""
    lines = _code_lines(simple_square_gcode)
    assert any(l.startswith("M3") for l in lines), "no M3 laser-on found"
    assert lines[-1].startswith("M5"), "program must end with the laser off"

    # Every G1 must sit inside an M3...M5 window.
    laser_on = False
    for line in lines:
        if line.startswith("M5"):
            laser_on = False
        elif line.startswith("M3"):
            laser_on = True
        elif line.startswith("G1"):
            assert laser_on, f"G1 emitted with laser off: {line!r}"


def test_moves_use_space_separated_axis_words(simple_square_gcode):
    """Vector moves are `G0 X<n> Y<n>` - the preview's regex assumes axis words."""
    for line in _code_lines(simple_square_gcode):
        if not MOVE_RE.match(line):
            continue
        assert re.search(r"\bX-?\d*\.?\d+", line) or re.search(r"\bY-?\d*\.?\d+", line), (
            f"move with no parseable axis word: {line!r}"
        )


def test_program_starts_and_ends_at_origin(simple_square_gcode):
    """The preview counts the opening move off (0,0) as real travel."""
    lines = _code_lines(simple_square_gcode)
    moves = [l for l in lines if MOVE_RE.match(l)]
    assert moves, "no moves emitted"
    assert moves[-1].replace(" ", "").startswith("G0X0Y0"), (
        f"program should return to origin, ended with {moves[-1]!r}"
    )


def test_power_word_is_s_on_the_m3_line(simple_square_gcode):
    """Power arrives as `M3 S<n>`; the preview reads S to detect S0 = off."""
    m3_lines = [l for l in _code_lines(simple_square_gcode) if l.startswith("M3")]
    assert m3_lines, "no M3 line"
    for line in m3_lines:
        assert re.search(r"\bS-?\d*\.?\d+", line), f"M3 without S power word: {line!r}"


def test_no_arc_commands_emitted(simple_square_gcode, curves_gcode):
    """The preview draws straight segments only.

    G2/G3 arcs are listed as future work (E5 in the review). If they land, the
    preview needs arc support before this test is relaxed.
    """
    for gcode in (simple_square_gcode, curves_gcode):
        for line in _code_lines(gcode):
            assert not re.match(r"^G0*[23]\b", line), f"unexpected arc command: {line!r}"
