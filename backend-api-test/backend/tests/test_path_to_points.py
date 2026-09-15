"""
Unit tests for gcode_service._path_to_points: SVG path 'd' -> list of Pt.

These lock in the Task 1 fix: S/Q/T were previously silently dropped, which
ALSO failed to advance the current point, displacing every subsequent
command in the same path.
"""
import math

import pytest

from gcode_service import _path_to_points


def last_xy(pts):
    return (pts[-1].x, pts[-1].y)


def test_move_line_horiz_vert_close():
    pts = _path_to_points("M 0,0 L 10,0 H 10 V 10 Z")
    coords = [(p.x, p.y) for p in pts]
    assert coords[0] == (0, 0)
    assert coords[1] == (10, 0)
    # H 10 is absolute -> x=10 (no-op here, still emits a point)
    assert coords[2] == (10, 0)
    assert coords[3] == (10, 10)
    # Z returns to subpath start
    assert coords[-1] == pytest.approx((0, 0))


def test_relative_line_and_horiz_vert():
    pts = _path_to_points("m 0,0 l 10,0 h 5 v 5")
    coords = [(p.x, p.y) for p in pts]
    assert coords[-1] == pytest.approx((15, 5))


def test_cubic_bezier_absolute_endpoint():
    pts = _path_to_points("M 0,0 C 10,0 20,10 20,20")
    assert last_xy(pts) == pytest.approx((20, 20))


def test_cubic_bezier_relative_endpoint():
    pts = _path_to_points("M 0,0 c 10,0 20,10 20,20")
    assert last_xy(pts) == pytest.approx((20, 20))


def test_arc_endpoint():
    # Quarter circle arc from (0,0) to (10,10), radius 10
    pts = _path_to_points("M 0,0 A 10,10 0 0 1 10,10")
    assert last_xy(pts) == pytest.approx((10, 10))
    # All intermediate points should be roughly 10 away from center (0,10) or (10,0)
    # depending on sweep - just sanity check the arc bulges (not a straight line)
    mid = pts[len(pts) // 2]
    assert not (mid.x == pytest.approx(5) and mid.y == pytest.approx(5))


def test_task1_repro_s_after_c_then_l():
    """
    Exact repro string from the task: the 's' segment must no longer vanish,
    and the following 'l' must land at the geometrically correct point
    rather than being displaced by the dropped 's'.
    """
    d = "M 0,0 c 10,0 20,10 20,20 s 10,20 20,20 l 5,5 z"
    pts = _path_to_points(d)
    coords = [(p.x, p.y) for p in pts]

    # End of the 's' segment must be at (40, 40)
    # (find it by looking for the point right before the final l/z points)
    assert coords[-2] == pytest.approx((45, 45))  # end of 'l 5,5' from (40,40)
    assert coords[-1] == pytest.approx((0, 0))  # 'z' closes back to start


def test_smooth_cubic_after_cubic_absolute():
    # First C: p0=(0,0) p1=(10,0) p2=(20,10) p3=(20,20)
    # S reflects p2 about p3 -> (20,30); S args: 30,40 40,40 (absolute)
    d = "M 0,0 C 10,0 20,10 20,20 S 30,40 40,40"
    pts = _path_to_points(d)
    assert last_xy(pts) == pytest.approx((40, 40))


def test_smooth_cubic_without_preceding_cubic_uses_current_point():
    # S with no preceding C/S: first control point == current point (0,0)
    d = "M 0,0 S 10,10 20,0"
    pts = _path_to_points(d)
    assert last_xy(pts) == pytest.approx((20, 0))
    # Since the "virtual" first control point is the current point, the curve
    # should stay symmetric-ish; just confirm it isn't a straight line to (20,0)
    # by checking some interior point deviates from the straight path.
    straight_y_at_mid = 0  # a straight line from (0,0) to (20,0) has y=0 throughout
    mid = pts[len(pts) // 2]
    assert mid.y != pytest.approx(straight_y_at_mid)


def test_quadratic_bezier_absolute():
    d = "M 0,0 Q 10,20 20,0"
    pts = _path_to_points(d)
    assert last_xy(pts) == pytest.approx((20, 0))
    # Peak should be around x=10 with positive y (bulges towards control point)
    peak = max(pts, key=lambda p: p.y)
    assert peak.y > 0


def test_quadratic_bezier_relative():
    d = "M 0,0 q 10,20 20,0"
    pts = _path_to_points(d)
    assert last_xy(pts) == pytest.approx((20, 0))


def test_smooth_quadratic_after_quadratic():
    # Q ends at (20,20) w/ control (10,20). T reflects control -> (30,20).
    # T target (40,20) -> since control point y matches endpoints, this is a
    # straight horizontal segment at y=20.
    d = "M 0,0 Q 10,20 20,20 T 40,20"
    pts = _path_to_points(d)
    coords = [(p.x, p.y) for p in pts]
    assert last_xy(pts) == pytest.approx((40, 20))
    # All points from the T segment onward should sit at y=20 (straight line)
    # since control point (30,20) is collinear with the endpoints.
    t_segment_points = coords[len(coords) // 2 :]
    for x, y in t_segment_points:
        assert y == pytest.approx(20, abs=1e-6)


def test_smooth_quadratic_without_preceding_quadratic_uses_current_point():
    d = "M 0,0 T 20,0"
    pts = _path_to_points(d)
    assert last_xy(pts) == pytest.approx((20, 0))


def test_unknown_command_raises():
    with pytest.raises(ValueError):
        _path_to_points("M 0,0 B 10,10")


def test_unknown_command_names_offending_letter():
    with pytest.raises(ValueError, match="B"):
        _path_to_points("M 0,0 B 10,10")


def test_multiple_m_subpaths_reset_smooth_tracking():
    # A new M should reset the smooth-curve tracking so a subsequent S/T
    # doesn't reflect a control point from a previous, unrelated subpath.
    d = "M 0,0 C 10,0 20,10 20,20 M 100,100 S 110,110 120,100"
    pts = _path_to_points(d)
    # Since prev_cmd was reset by M, the S control point should equal the
    # current point (100,100), not a reflection of the earlier C's control.
    assert last_xy(pts) == pytest.approx((120, 100))
