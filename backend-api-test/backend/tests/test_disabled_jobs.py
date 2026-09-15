"""A job list that resolves to nothing must cut nothing.

generate_vector_gcode_advanced used to fall back to the whole-document global
path whenever no job survived filtering. Disabling every layer, or sending a
colour that matched nothing, therefore produced a full-power cut of every path
in the file - the opposite of what the operator selected.
"""
import re
from pathlib import Path

import pytest

import gcode_service as gs

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SVG = str(FIXTURES_DIR / "scattered_shapes.svg")

MATCHING = "#ff0000"  # the stroke colour used in scattered_shapes.svg


def _cut_moves(gcode):
    """G1 moves emitted while the laser is on."""
    cuts = 0
    laser_on = False
    for raw in gcode.splitlines():
        line = raw.split(";")[0].strip()
        if not line:
            continue
        if re.match(r"^M0*5\b", line):
            laser_on = False
        elif re.match(r"^M0*[34]\b", line):
            laser_on = True
        elif re.match(r"^G0*1\b", line) and laser_on:
            cuts += 1
    return cuts


@pytest.mark.parametrize(
    "jobs,label",
    [
        ([{"color": MATCHING, "enabled": False, "speed": 1500, "power": 70, "passes": 1}],
         "every layer disabled"),
        ([{"color": "#00ff00", "enabled": True, "speed": 1500, "power": 70, "passes": 1}],
         "colour matches nothing in the document"),
        ([{"color": None, "enabled": True, "speed": 1500, "power": 70, "passes": 1}],
         "unusable colour"),
    ],
)
def test_no_enabled_jobs_cuts_nothing(jobs, label):
    gcode = gs.generate_vector_gcode_advanced(svg_path=SVG, jobs=jobs)
    assert _cut_moves(gcode) == 0, f"{label}: emitted cutting moves"
    assert "M3" not in gcode, f"{label}: laser was enabled"


def test_enabled_job_still_cuts():
    """The guard must not break the normal path."""
    jobs = [{"color": MATCHING, "enabled": True, "speed": 1500, "power": 70, "passes": 1}]
    gcode = gs.generate_vector_gcode_advanced(svg_path=SVG, jobs=jobs)
    assert _cut_moves(gcode) > 0
    assert "M3" in gcode


def test_passes_are_honoured():
    """Regression guard: 4 passes must emit 4x the cutting moves of 1 pass."""
    def cuts_for(passes):
        jobs = [{"color": MATCHING, "enabled": True, "speed": 1500,
                 "power": 70, "passes": passes}]
        return _cut_moves(gs.generate_vector_gcode_advanced(svg_path=SVG, jobs=jobs))

    assert cuts_for(4) == cuts_for(1) * 4


def test_omitted_jobs_keeps_legacy_whole_file_behaviour():
    """Callers that pass no jobs at all still get the global fallback."""
    for empty in (None, []):
        gcode = gs.generate_vector_gcode_advanced(svg_path=SVG, jobs=empty)
        assert _cut_moves(gcode) > 0, "legacy no-jobs callers should still cut"
