"""
Benchmark (NOT a pytest test -- no `test_*` functions here, and it is not
collected by the suite) measuring the effect of the toolpath-ordering,
adaptive-flattening and simplification work on real generated G-code.

Run directly:
    ./.venv/bin/python backend-api-test/backend/tests/benchmark_toolpath.py

For each fixture, generates G-code twice:
  - "before": Task 1 (path reordering) and Task 4 (simplification) disabled,
    and Task 3 (adaptive Bezier flattening) forced back to the old fixed
    8-segments-per-curve behavior, via monkeypatching -- i.e. as close as
    practical to the pre-optimization code path, without needing to check
    out the old revision.
  - "after": the current code, unmodified.

Reports, per fixture:
  - total rapid (G0) distance, mm
  - total cut (G1) distance, mm       <- correctness canary: must barely move
  - emitted G0+G1 line count
  - the header's reported estimated minutes (`;$M Time`, rounded to a whole
    minute -- shown mainly to demonstrate it is a coarse, and for rapid time,
    structurally blind metric; see note below)
  - a more precise estimate computed here by actually summing G1/speed +
    G0/RAPID_SPEED over the emitted G-code text, which DOES reflect the
    ordering improvement

NOTE on the header time estimate: `_generate_gcode_from_job_batches` (and the
legacy `_generate_gcode_from_paths`) compute `est_min` by resetting their
running position to None at the start of EACH path, so inter-path rapid
travel was never counted even before this change -- a pre-existing gap, not
something introduced here. Fixing that estimator is out of scope for this
pass (changing it would also change the exact value asserted by
`tests/test_time_estimate.py`, a locked-in regression test for an unrelated
bug fix). This benchmark's own "computed estimate" column is the honest
number; the header's `;$M Time` is reported for completeness but is expected
to stay essentially flat across before/after.
"""
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import gcode_service as gs  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"

FIXTURES = [
    ("simple_square.svg", [{"color": "#ff0000", "enabled": True, "speed": 1000, "power": 50, "passes": 1}]),
    ("group_transform.svg", [{"color": "#0000ff", "enabled": True, "speed": 1000, "power": 60, "passes": 1}]),
    ("curves_sqt.svg", [{"color": "#00ff00", "enabled": True, "speed": 800, "power": 40, "passes": 1}]),
    ("scattered_shapes.svg", [{"color": "#ff0000", "enabled": True, "speed": 1500, "power": 70, "passes": 1}]),
    ("scattered_shapes.svg", [{"color": "#ff0000", "enabled": True, "speed": 1500, "power": 70, "passes": 4}]),
    ("redundant_points.svg", [{"color": "#ff0000", "enabled": True, "speed": 1000, "power": 50, "passes": 1}]),
]


def _identity_optimize(paths, start_point=(0.0, 0.0)):
    return list(paths)


def _identity_simplify(pts, tolerance):
    return pts


def _fixed_cubic_segs(p0, p1, p2, p3, tol):
    return 8


def _fixed_quad_segs(p0, p1, p2, tol):
    return 8


def _tiny_thumb(segments, bounds, max_w=1, max_h=1):
    return 1, 1, ["FF"]


def _measure(gcode: str):
    rapid_mm = 0.0
    cut_mm = 0.0
    line_count = 0
    # Machine starts at the origin; the first move off it is real travel.
    # Starting from None silently dropped it from the totals.
    last = (0.0, 0.0)
    reported_minutes = None
    computed_minutes = 0.0

    for raw in gcode.splitlines():
        line = raw.strip()
        m = re.match(r";\$M Time (\d+)", line)
        if m:
            reported_minutes = int(m.group(1))
            continue
        if not (line.startswith("G0") or line.startswith("G1")):
            continue
        line_count += 1
        x = y = None
        for tok in line.split():
            if tok.startswith("X"):
                x = float(tok[1:])
            elif tok.startswith("Y"):
                y = float(tok[1:])
        if x is None or y is None:
            continue
        cur = (x, y)
        if last is not None:
            d = gs._dist(last, cur)
            if line.startswith("G0"):
                rapid_mm += d
                computed_minutes += d / gs.RAPID_SPEED
            else:
                cut_mm += d
                # speed varies per job; approximate using F<speed> lines we saw
        last = cur

    return {
        "rapid_mm": rapid_mm,
        "cut_mm": cut_mm,
        "lines": line_count,
        "reported_min": reported_minutes,
    }


def _measure_with_feed(gcode: str):
    """Like _measure, but tracks the active F<speed> to get an accurate G1 time."""
    rapid_mm = 0.0
    cut_mm = 0.0
    line_count = 0
    # Machine starts at the origin; the first move off it is real travel.
    # Starting from None silently dropped it from the totals.
    last = (0.0, 0.0)
    reported_minutes = None
    computed_minutes = 0.0
    feed = 1000.0

    for raw in gcode.splitlines():
        line = raw.strip()
        m = re.match(r";\$M Time (\d+)", line)
        if m:
            reported_minutes = int(m.group(1))
            continue
        fm = re.match(r"F(\d+(?:\.\d+)?)", line)
        if fm:
            feed = float(fm.group(1))
            continue
        if not (line.startswith("G0") or line.startswith("G1")):
            continue
        line_count += 1
        x = y = None
        for tok in line.split():
            if tok.startswith("X"):
                x = float(tok[1:])
            elif tok.startswith("Y"):
                y = float(tok[1:])
        if x is None or y is None:
            continue
        cur = (x, y)
        if last is not None:
            d = gs._dist(last, cur)
            if line.startswith("G0"):
                rapid_mm += d
                computed_minutes += d / gs.RAPID_SPEED
            else:
                cut_mm += d
                computed_minutes += d / feed
        last = cur

    return {
        "rapid_mm": rapid_mm,
        "cut_mm": cut_mm,
        "lines": line_count,
        "reported_min": reported_minutes,
        "computed_min": computed_minutes,
    }


def run_case(svg_name, jobs, before: bool):
    svg_path = FIXTURES_DIR / svg_name
    gcode = gs.generate_vector_gcode_advanced(str(svg_path), jobs, origin="bottom-left")
    return _measure_with_feed(gcode)


def main():
    orig = {
        "_optimize_path_order": gs._optimize_path_order,
        "_simplify_pts": gs._simplify_pts,
        "_cubic_seg_count": gs._cubic_seg_count,
        "_quad_seg_count": gs._quad_seg_count,
        "_make_thumbnail_rows": gs._make_thumbnail_rows,
    }
    gs._make_thumbnail_rows = _tiny_thumb

    rows = []
    for svg_name, jobs in FIXTURES:
        label = f"{svg_name} (passes={jobs[0]['passes']})"

        # BEFORE: disable Task 1 + 4, force Task 3 back to fixed segs=8.
        gs._optimize_path_order = _identity_optimize
        gs._simplify_pts = _identity_simplify
        gs._cubic_seg_count = _fixed_cubic_segs
        gs._quad_seg_count = _fixed_quad_segs
        before = run_case(svg_name, jobs, before=True)

        # AFTER: current code.
        gs._optimize_path_order = orig["_optimize_path_order"]
        gs._simplify_pts = orig["_simplify_pts"]
        gs._cubic_seg_count = orig["_cubic_seg_count"]
        gs._quad_seg_count = orig["_quad_seg_count"]
        after = run_case(svg_name, jobs, before=False)

        rows.append((label, before, after))

    gs._make_thumbnail_rows = orig["_make_thumbnail_rows"]

    hdr = (
        f"{'fixture':<32} {'metric':<16} {'before':>12} {'after':>12} {'delta':>10}"
    )
    print(hdr)
    print("-" * len(hdr))
    for label, before, after in rows:
        for key, fmt in [
            ("rapid_mm", "{:.1f} mm"),
            ("cut_mm", "{:.1f} mm"),
            ("lines", "{:d}"),
            ("reported_min", "{} min"),
            ("computed_min", "{:.4f} min"),
        ]:
            b = before[key]
            a = after[key]
            if b is None or a is None:
                bstr, astr, dstr = "n/a", "n/a", "n/a"
            else:
                bstr = fmt.format(b)
                astr = fmt.format(a)
                try:
                    dstr = fmt.format(a - b)
                except Exception:
                    dstr = "n/a"
            print(f"{label:<32} {key:<16} {bstr:>12} {astr:>12} {dstr:>10}")
        print()


if __name__ == "__main__":
    main()
