"""
Regression test for the Task 3 bug: a per-job `passes` multiplier was applied
to the SHARED running time accumulator instead of that job's own
contribution, so time compounded across jobs instead of adding.

Confirmed example from the task: two jobs, each a 100mm cut at 1000 mm/min,
passes 1 and 3. Buggy code reports 0.6 min; correct is 0.4 min:
  job1: 100/1000 = 0.1 min, *1 pass = 0.1
  job2: 100/1000 = 0.1 min, *3 passes = 0.3
  total = 0.4 min

(Buggy behavior for reference: est=0.1 after job1 (*1=0.1), then
est += 0.1 -> 0.2, then est *= 3 -> 0.6.)
"""
import pytest

from gcode_service import Mat, _generate_gcode_from_job_batches, _make_meta_header


def test_two_jobs_time_does_not_compound(monkeypatch):
    captured = {}
    original = _make_meta_header

    def spy(bounds, estimated_minutes, *args, **kwargs):
        captured["estimated_minutes"] = estimated_minutes
        return original(bounds, estimated_minutes, *args, **kwargs)

    monkeypatch.setattr("gcode_service._make_meta_header", spy)

    batches = [
        {
            "color": "#ff0000",
            "paths": [("M 0,0 L 100,0", Mat())],
            "speed": 1000,
            "power": 100.0,
            "passes": 1,
        },
        {
            "color": "#00ff00",
            "paths": [("M 0,0 L 100,0", Mat())],
            "speed": 1000,
            "power": 100.0,
            "passes": 3,
        },
    ]

    _generate_gcode_from_job_batches(
        batches=batches,
        svg_h_mm=285.0,
        scale_x=1.0,
        scale_y=1.0,
        origin="bottom-left",
    )

    assert captured["estimated_minutes"] == pytest.approx(0.4, abs=1e-9)
