"""
Laser-safety invariants on generated G-code output.

These are the invariants that actually matter physically: the laser must
never be left on while rapiding (G0), and a generated file must never end
with the laser still on.
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


def _laser_state_trace(gcode: str):
    """
    Walk the G-code lines and yield (laser_on_before_this_line, line) for
    every G0/G1/M3/M5 line, tracking laser on/off state as we go.
    """
    laser_on = False
    for raw in gcode.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        cmd = line.split()[0]
        if cmd.startswith("M3"):
            yield laser_on, line
            laser_on = True
        elif cmd.startswith("M5"):
            yield laser_on, line
            laser_on = False
        elif cmd.startswith("G0"):
            yield laser_on, line
        elif cmd.startswith("G1"):
            yield laser_on, line


@pytest.mark.parametrize(
    "svg_name,jobs",
    [
        (
            "simple_square.svg",
            [{"color": "#ff0000", "enabled": True, "speed": 1000, "power": 50, "passes": 1}],
        ),
        (
            "curves_sqt.svg",
            [{"color": "#00ff00", "enabled": True, "speed": 800, "power": 40, "passes": 1}],
        ),
        (
            "group_transform.svg",
            [{"color": "#0000ff", "enabled": True, "speed": 1000, "power": 60, "passes": 3}],
        ),
    ],
)
def test_g0_never_happens_with_laser_on(svg_name, jobs):
    svg_path = FIXTURES_DIR / svg_name
    gcode = gs.generate_vector_gcode_advanced(str(svg_path), jobs, origin="bottom-left")

    for laser_on_before, line in _laser_state_trace(gcode):
        if line.startswith("G0"):
            assert not laser_on_before, f"G0 rapid issued while laser still on: {line!r}"


@pytest.mark.parametrize(
    "svg_name,jobs",
    [
        (
            "simple_square.svg",
            [{"color": "#ff0000", "enabled": True, "speed": 1000, "power": 50, "passes": 1}],
        ),
        (
            "curves_sqt.svg",
            [{"color": "#00ff00", "enabled": True, "speed": 800, "power": 40, "passes": 1}],
        ),
    ],
)
def test_file_ends_with_laser_off(svg_name, jobs):
    svg_path = FIXTURES_DIR / svg_name
    gcode = gs.generate_vector_gcode_advanced(str(svg_path), jobs, origin="bottom-left")

    laser_on = False
    for _before, line in _laser_state_trace(gcode):
        cmd = line.split()[0]
        if cmd.startswith("M3"):
            laser_on = True
        elif cmd.startswith("M5"):
            laser_on = False
    assert not laser_on, "Generated G-code does not end with the laser off"

    # Also require the file to literally contain a final laser-off command,
    # matching the header's initial safe-start M5.
    non_empty_lines = [l for l in gcode.splitlines() if l.strip()]
    assert non_empty_lines[-1].strip().startswith("M5"), "Last line must be M5 (laser off)"


def test_m3_and_m5_counts_balanced_per_job():
    """
    Every M3 (laser on) must be matched by exactly one M5 (laser off) later
    in the file - no dangling "on" state. There's also one extra M5 at the
    very start of the file (the unconditional safe-start header, before any
    M3 has happened), independent of how many M3/pass pairs follow.
    """
    svg_path = FIXTURES_DIR / "simple_square.svg"
    jobs = [{"color": "#ff0000", "enabled": True, "speed": 1000, "power": 50, "passes": 2}]
    gcode = gs.generate_vector_gcode_advanced(str(svg_path), jobs, origin="bottom-left")

    lines = [l.strip() for l in gcode.splitlines() if l.strip()]
    m3_count = sum(1 for l in lines if l.startswith("M3"))
    m5_count = sum(1 for l in lines if l.startswith("M5"))
    # 2 passes -> 2 M3/M5 pairs (one per pass), plus the safe-start M5 header
    # (laser off, before any M3) and the safe-end M5 footer (laser off, after
    # the last M3) that bracket the whole file.
    assert m3_count == 2
    assert m5_count == m3_count + 2
    # The very first M-code line (after the metadata comment block) is the
    # safe-start M5, before any M3 has occurred.
    first_mcode_line = next(l for l in lines if l.startswith("M3") or l.startswith("M5"))
    assert first_mcode_line.startswith("M5")
    # And the file must end on M5 too (laser definitively off).
    assert lines[-1].startswith("M5")
