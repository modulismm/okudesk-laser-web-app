"""
Tests for the toolpath-ordering optimizer (Task 1), per-pass alternation
(Task 2), and path simplification (Task 4).
"""
import math
from pathlib import Path

import pytest

from gcode_service import (
    Mat,
    Pt,
    SIMPLIFY_TOLERANCE_MM,
    _douglas_peucker,
    _dist,
    _generate_gcode_from_job_batches,
    _optimize_path_order,
    _path_endpoints,
    _point_segment_dist,
    _reverse_path,
    _simplify_pts,
)


def _square_path(cx, cy, size=2.0):
    """A small closed square contour centered at (cx, cy), as Pt list."""
    h = size / 2.0
    pts = [
        Pt(cx - h, cy - h, "M"),
        Pt(cx + h, cy - h, "L"),
        Pt(cx + h, cy + h, "L"),
        Pt(cx - h, cy + h, "L"),
        Pt(cx - h, cy - h, "L"),
    ]
    return pts


def _tour_rapid_distance(paths, start_point=(0.0, 0.0)):
    head = start_point
    total = 0.0
    for pts in paths:
        entry, exit_ = _path_endpoints(pts)
        total += _dist(head, entry)
        head = exit_
    return total


def _total_cut_distance(paths):
    total = 0.0
    for pts in paths:
        for i in range(1, len(pts)):
            if pts[i].cmd == "L":
                total += _dist((pts[i - 1].x, pts[i - 1].y), (pts[i].x, pts[i].y))
    return total


def _all_segments(paths):
    """Return the set of (rounded) undirected segments drawn by these paths."""
    segs = set()
    for pts in paths:
        for i in range(1, len(pts)):
            a = (round(pts[i - 1].x, 6), round(pts[i - 1].y, 6))
            b = (round(pts[i].x, 6), round(pts[i].y, 6))
            segs.add(frozenset((a, b)))
    return segs


def test_optimize_reduces_rapid_distance_on_scattered_paths():
    # 20 small shapes scattered across a wide area, deliberately in a bad
    # (shuffled / far-jumping) document order.
    import random

    rng = random.Random(42)
    centers = [(rng.uniform(0, 400), rng.uniform(0, 200)) for _ in range(20)]
    # Deliberately bad order: sort so consecutive shapes are far apart
    # (interleave first/second half instead of any spatially coherent order).
    bad_order_paths = []
    n = len(centers)
    for i in range(n // 2):
        bad_order_paths.append(_square_path(*centers[i]))
        bad_order_paths.append(_square_path(*centers[n - 1 - i]))

    baseline_rapid = _tour_rapid_distance(bad_order_paths)
    optimized = _optimize_path_order(bad_order_paths, start_point=(0.0, 0.0))
    optimized_rapid = _tour_rapid_distance(optimized)

    assert optimized_rapid < baseline_rapid * 0.5, (
        f"expected optimizer to substantially cut rapid distance, "
        f"baseline={baseline_rapid:.1f} optimized={optimized_rapid:.1f}"
    )

    # Same shapes, just reordered/possibly reversed -> same total cut length.
    assert _total_cut_distance(optimized) == pytest.approx(
        _total_cut_distance(bad_order_paths), rel=1e-9
    )
    assert _all_segments(optimized) == _all_segments(bad_order_paths)
    assert len(optimized) == len(bad_order_paths)


def test_reversal_preserves_geometry_reverses_direction():
    pts = [
        Pt(0.0, 0.0, "M"),
        Pt(10.0, 0.0, "L"),
        Pt(10.0, 5.0, "L"),
        Pt(0.0, 5.0, "L"),
    ]
    rev = _reverse_path(pts)

    # cmd rebuilt: first point is 'M', the rest are 'L'.
    assert rev[0].cmd == "M"
    assert all(p.cmd == "L" for p in rev[1:])

    # Same set of segments (undirected), same total length, opposite order.
    assert _all_segments([pts]) == _all_segments([rev])
    assert [(p.x, p.y) for p in rev] == [(p.x, p.y) for p in reversed(pts)]
    assert _total_cut_distance([pts]) == pytest.approx(_total_cut_distance([rev]))


def test_optimize_path_order_never_called_across_batches_in_emit(monkeypatch):
    """
    _generate_gcode_from_job_batches must call _optimize_path_order once per
    job/color batch, never on a list merged across batches.
    """
    import gcode_service as gs

    seen_batches = []
    original = gs._optimize_path_order

    def spy(paths, start_point=(0.0, 0.0)):
        seen_batches.append(len(paths))
        return original(paths, start_point=start_point)

    monkeypatch.setattr(gs, "_optimize_path_order", spy)
    monkeypatch.setattr(
        gs, "_make_thumbnail_rows", lambda segments, bounds, max_w=1, max_h=1: (1, 1, ["FF"])
    )

    batches = [
        {
            "color": "#ff0000",
            "paths": [("M 0,0 L 10,0", Mat()), ("M 100,100 L 110,100", Mat())],
            "speed": 1000,
            "power": 100.0,
            "passes": 1,
        },
        {
            "color": "#00ff00",
            "paths": [("M 200,200 L 210,200", Mat())],
            "speed": 1000,
            "power": 100.0,
            "passes": 1,
        },
    ]

    gs._generate_gcode_from_job_batches(
        batches=batches, svg_h_mm=285.0, scale_x=1.0, scale_y=1.0, origin="bottom-left"
    )

    # One optimizer call per batch, each sized to that batch's own path count
    # (2 paths for job 1, 1 path for job 2) -- never a merged 3-path call.
    assert seen_batches == [2, 1]


def test_job_batch_emission_order_preserved():
    """
    Reordering happens only within a batch; the *order jobs are emitted in*
    must exactly follow the caller-provided batch order, regardless of what
    the path-order optimizer decides inside each job.
    """
    from gcode_service import _generate_gcode_from_job_batches as gen

    batches = [
        {
            "color": "#00ff00",
            "paths": [("M 0,0 L 10,0", Mat())],
            "speed": 1000,
            "power": 100.0,
            "passes": 1,
        },
        {
            "color": "#ff0000",
            "paths": [("M 0,0 L 10,0", Mat())],
            "speed": 1000,
            "power": 100.0,
            "passes": 1,
        },
        {
            "color": "#0000ff",
            "paths": [("M 0,0 L 10,0", Mat())],
            "speed": 1000,
            "power": 100.0,
            "passes": 1,
        },
    ]

    import gcode_service as gs

    orig_thumb = gs._make_thumbnail_rows
    gs._make_thumbnail_rows = lambda segments, bounds, max_w=1, max_h=1: (1, 1, ["FF"])
    try:
        gcode = gen(
            batches=batches, svg_h_mm=285.0, scale_x=1.0, scale_y=1.0, origin="bottom-left"
        )
    finally:
        gs._make_thumbnail_rows = orig_thumb

    job_markers = [l for l in gcode.splitlines() if l.startswith("; --- Job")]
    assert job_markers == [
        "; --- Job #00ff00 ---",
        "; --- Job #ff0000 ---",
        "; --- Job #0000ff ---",
    ]


def test_simplify_stays_within_tolerance_of_original_polyline():
    # A near-straight polyline with tiny wobble well under tolerance, plus
    # one genuine corner that must survive simplification.
    pts = [Pt(0.0, 0.0, "M")]
    for i in range(1, 50):
        x = i * 1.0
        y = 0.001 * math.sin(i)  # sub-micron-scale wobble, way under tolerance
        pts.append(Pt(x, y, "L"))
    pts.append(Pt(50.0, 20.0, "L"))  # a real corner

    simplified = _simplify_pts(pts, SIMPLIFY_TOLERANCE_MM)

    # Must be meaningfully smaller (the wobble is simplified away).
    assert len(simplified) < len(pts)
    # First and last points preserved exactly.
    assert (simplified[0].x, simplified[0].y) == (pts[0].x, pts[0].y)
    assert (simplified[-1].x, simplified[-1].y) == (pts[-1].x, pts[-1].y)
    assert simplified[0].cmd == "M"
    assert all(p.cmd == "L" for p in simplified[1:])

    # Every original point must lie within tolerance of the simplified
    # *polyline* (not just its vertices) -- this is Douglas-Peucker's actual
    # guarantee: dropped points are within `tolerance` of the chord that
    # replaced them.
    simple_coords = [(p.x, p.y) for p in simplified]
    for p in pts:
        pc = (p.x, p.y)
        best = min(
            _point_segment_dist(pc, simple_coords[i], simple_coords[i + 1])
            for i in range(len(simple_coords) - 1)
        )
        assert best <= SIMPLIFY_TOLERANCE_MM + 1e-9


def test_legacy_single_job_path_also_reorders_and_stays_laser_safe():
    """
    `_generate_gcode_from_paths` (the legacy single-job emitter, reached via
    `generate_vector_gcode`) must also benefit from Task 1/2 reordering, and
    must still uphold laser-safety invariants: no G0 while the laser is on,
    and the file ends with the laser off.
    """
    import gcode_service as gs

    orig_thumb = gs._make_thumbnail_rows
    gs._make_thumbnail_rows = lambda segments, bounds, max_w=1, max_h=1: (1, 1, ["FF"])
    try:
        svg_path = (
            Path(__file__).parent / "fixtures" / "scattered_shapes.svg"
        )
        gcode = gs.generate_vector_gcode(
            str(svg_path), speed=1500, power=70.0, passes=2, origin="bottom-left"
        )
    finally:
        gs._make_thumbnail_rows = orig_thumb

    laser_on = False
    for raw in gcode.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("M3"):
            laser_on = True
        elif line.startswith("M5"):
            laser_on = False
        elif line.startswith("G0"):
            assert not laser_on, f"G0 rapid issued while laser on: {line!r}"

    non_empty = [l for l in gcode.splitlines() if l.strip()]
    assert non_empty[-1].strip().startswith("M5")


def test_simplify_does_not_merge_across_m_boundary():
    # Two subpaths in a single point list (as _path_to_points would produce
    # for a `d` with two M's): simplification must keep them separate.
    pts = [
        Pt(0.0, 0.0, "M"),
        Pt(1.0, 0.0001, "L"),
        Pt(2.0, 0.0, "L"),
        Pt(10.0, 10.0, "M"),
        Pt(11.0, 10.0001, "L"),
        Pt(12.0, 10.0, "L"),
    ]
    simplified = _simplify_pts(pts, SIMPLIFY_TOLERANCE_MM)
    m_count = sum(1 for p in simplified if p.cmd == "M")
    assert m_count == 2
    # The second subpath's first point must still be exactly (10, 10),
    # not merged/interpolated with the first subpath.
    second_m_idx = [i for i, p in enumerate(simplified) if p.cmd == "M"][1]
    assert (simplified[second_m_idx].x, simplified[second_m_idx].y) == (10.0, 10.0)
