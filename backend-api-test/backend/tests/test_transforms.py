"""
Unit tests for gcode_service._parse_transform / _apply_mat_to_points.
"""
import math

import pytest
from lxml import etree

from gcode_service import (
    Mat,
    Pt,
    _apply_mat_to_points,
    _extract_drawables,
    _parse_transform,
)


def test_translate():
    m = _parse_transform("translate(10, 5)")
    assert m.apply(0, 0) == pytest.approx((10, 5))
    assert m.apply(1, 1) == pytest.approx((11, 6))


def test_translate_single_arg():
    m = _parse_transform("translate(10)")
    assert m.apply(0, 0) == pytest.approx((10, 0))


def test_scale():
    m = _parse_transform("scale(2, 3)")
    assert m.apply(1, 1) == pytest.approx((2, 3))


def test_scale_uniform():
    m = _parse_transform("scale(2)")
    assert m.apply(1, 1) == pytest.approx((2, 2))


def test_rotate_90_about_origin():
    m = _parse_transform("rotate(90)")
    x, y = m.apply(1, 0)
    assert x == pytest.approx(0, abs=1e-9)
    assert y == pytest.approx(1, abs=1e-9)


def test_rotate_about_point():
    # Rotating 180 degrees about (10, 10) should map (10, 0) -> (10, 20)
    m = _parse_transform("rotate(180, 10, 10)")
    x, y = m.apply(10, 0)
    assert x == pytest.approx(10, abs=1e-9)
    assert y == pytest.approx(20, abs=1e-9)


def test_matrix():
    # matrix(a b c d e f) is the identity-plus-translate here
    m = _parse_transform("matrix(1,0,0,1,5,7)")
    assert m.apply(0, 0) == pytest.approx((5, 7))


def test_combined_translate_then_scale_order():
    # SVG transform="A B" composes as matrix A*B, i.e. a point is transformed
    # by B first (the rightmost/innermost transform), then by A. So
    # "translate(10,0) scale(2)" scales first, then translates.
    m = _parse_transform("translate(10,0) scale(2)")
    assert m.apply(0, 0) == pytest.approx((10, 0))
    assert m.apply(1, 1) == pytest.approx((12, 2))


def test_apply_mat_to_points():
    pts = [Pt(1, 1, "M"), Pt(2, 2, "L")]
    m = _parse_transform("translate(10,10)")
    out = _apply_mat_to_points(pts, m)
    assert [(p.x, p.y) for p in out] == [pytest.approx((11, 11)), pytest.approx((12, 12))]
    assert [p.cmd for p in out] == ["M", "L"]


def test_nested_group_transform_accumulates():
    svg = etree.fromstring(
        b"""
        <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
          <g transform="translate(10,0)">
            <g transform="scale(2)">
              <path d="M 0,0 L 1,1" />
            </g>
          </g>
        </svg>
        """
    )
    drawables = _extract_drawables(svg)
    assert len(drawables) == 1
    el, mat = drawables[0]
    # Inner scale(2) applied first (closest to element), then outer translate(10,0):
    # point (1,1) -> scale -> (2,2) -> translate -> (12,2)
    assert mat.apply(1, 1) == pytest.approx((12, 2))
    assert mat.apply(0, 0) == pytest.approx((10, 0))
