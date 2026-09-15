"""Shape discovery and colour resolution must match svg-parser.js.

Two parsers exist - frontend/svg-parser.js builds the job list, gcode_service
re-parses the same file to emit G-code. When they disagree the failure is
silent: the UI offers a layer the backend cannot resolve, and the job cuts
nothing. These tests pin the backend half of that contract.
"""
from pathlib import Path

import pytest
from lxml import etree

import gcode_service as gs

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def colors_in(svg_name):
    root = etree.fromstring((FIXTURES_DIR / svg_name).read_bytes())
    found = []
    for el, _mat in gs._extract_drawables(root):
        c = gs._element_color(el)
        if c:
            found.append(c)
    return found


def test_stroke_inherited_from_parent_group():
    """Editors set stroke on a <g> and leave the shapes bare."""
    colors = colors_in("inherited_stroke.svg")
    assert colors == ["#ff0000", "#ff0000"], (
        "shapes inheriting stroke from a parent <g> must resolve to that colour"
    )


def test_shapes_inside_a_and_switch_are_found():
    """Recursion must not be limited to <g>."""
    colors = colors_in("nested_containers.svg")
    assert "#00ff00" in colors, "shape inside <a> was not found"
    assert "#0000ff" in colors, "shape inside <switch> was not found"


def test_clippath_contents_are_not_cut():
    """A <clipPath> shape is never rendered, so it must never be cut."""
    root = etree.fromstring((FIXTURES_DIR / "nested_containers.svg").read_bytes())
    drawables = gs._extract_drawables(root)
    for el, _ in drawables:
        parent = el.getparent()
        while parent is not None:
            assert gs._local_name(parent) not in gs._NON_RENDERED_CONTAINERS, (
                f"{gs._local_name(el)} inside <{gs._local_name(parent)}> should be skipped"
            )
            parent = parent.getparent()


def test_stroke_takes_precedence_over_fill():
    root = etree.fromstring(
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<path d="M0,0 L1,1" stroke="#ff0000" fill="#00ff00"/></svg>'
    )
    el = gs._extract_drawables(root)[0][0]
    assert gs._element_color(el) == "#ff0000"


def test_fill_used_when_no_stroke_anywhere():
    root = etree.fromstring(
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<path d="M0,0 L1,1" fill="#00ff00"/></svg>'
    )
    el = gs._extract_drawables(root)[0][0]
    assert gs._element_color(el) == "#00ff00"


def test_inherited_stroke_beats_own_fill():
    """CSS semantics: stroke resolves up the tree, and stroke wins over fill."""
    root = etree.fromstring(
        b'<svg xmlns="http://www.w3.org/2000/svg"><g stroke="#ff0000">'
        b'<path d="M0,0 L1,1" fill="#00ff00"/></g></svg>'
    )
    el = gs._extract_drawables(root)[0][0]
    assert gs._element_color(el) == "#ff0000"


def test_stroke_none_on_element_falls_through_to_ancestor():
    root = etree.fromstring(
        b'<svg xmlns="http://www.w3.org/2000/svg"><g stroke="#ff0000">'
        b'<path d="M0,0 L1,1" stroke="none"/></g></svg>'
    )
    el = gs._extract_drawables(root)[0][0]
    assert gs._element_color(el) == "#ff0000"


def test_no_colour_anywhere_returns_none():
    root = etree.fromstring(
        b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0,0 L1,1"/></svg>'
    )
    el = gs._extract_drawables(root)[0][0]
    assert gs._element_color(el) is None


def test_existing_fixtures_still_resolve():
    """The change must not alter files that already worked."""
    assert colors_in("simple_square.svg") == ["#ff0000"]
    assert colors_in("group_transform.svg") == ["#0000ff"]
