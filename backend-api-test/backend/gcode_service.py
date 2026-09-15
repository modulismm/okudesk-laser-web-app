"""
Service de génération G-code
Implémentation minimale autonome (sans Inkscape) pour permettre des tests rapides.

Objectif:
- Lire un SVG
- Extraire les chemins (au minimum: <path d="...">)
- Générer du G-code compatible OKU Desk (Smoothieware modifié)

Notes:
- Ceci ne remplace pas l'intégration complète des scripts Inkscape originaux.
- Transformations SVG avancées (transform=..., arcs A, etc.) ne sont pas encore supportées.
"""

from pathlib import Path
import math
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from lxml import etree
import base64
from io import BytesIO


MM_PER_INCH = 25.4
DPI = 96.0
MM_PER_PX = MM_PER_INCH / DPI

BED_W_MM = 500.0
BED_H_MM = 285.0

RAPID_SPEED = 7000  # mm/min
S_MAX = 255  # Power scale (0-255) on OKU
ZERO_MOVE_THRESHOLD = 0.005  # mm

THUMB_MAX_W = 225
THUMB_MAX_H = 159

ALLOWED_ORIGINS = (
    "bottom-left",
    "bottom-right",
    "top-left",
    "top-right",
    "center",
    "custom",
)

MAX_RASTER_PIXELS_PER_LINE = 80
RASTER_ZERO_MOVE_THRESHOLD_MM = 0.005
RASTER_PROTO_VERSION = "0.2.0"

# --- Toolpath ordering (path-order optimization) ---
# Above this many paths in a single job/color batch, skip the 2-opt
# improvement pass entirely (greedy nearest-neighbour still runs). Bounds
# worst-case request latency on pathological files with huge path counts.
# Measured on this codebase's pure-Python 2-opt: ~1-2s at 500 paths but
# growing sharply past that (multiple full O(n^2) sweeps), so 500 -- not the
# 2000 suggested as a starting point in the task description -- is what
# actually keeps a single generate-request's added latency in a
# "noticeable but not a timeout risk" range.
TWO_OPT_MAX_PATHS = 500
# Bounded number of full O(n^2) improvement sweeps. Kept modest (rather than
# running to full convergence) because each sweep is O(n^2) pure-Python
# distance comparisons: at n=800 a single sweep is already ~1-2s, so an
# unbounded number of sweeps on a large, still-improvable batch could turn
# into many seconds of request latency. Greedy nearest-neighbour (run
# unconditionally, uncapped) already gets most of the win; 2-opt here is a
# bounded "polish" pass, not a full local-optimum search.
TWO_OPT_MAX_PASSES = 4
# Hard cap on total accepted 2-opt swaps across all sweeps, in case of a
# pathological case that keeps finding (tiny) improvements.
TWO_OPT_MAX_SWAPS = 1000

# --- Adaptive Bezier flattening (Task 3) ---
# Target chord-error tolerance, in mm, for flattening cubic/quadratic Bezier
# curves. Comfortably below the machine's stated 0.1mm accuracy.
CURVE_TOLERANCE_MM = 0.05
_MIN_BEZIER_SEGS = 2
_MAX_BEZIER_SEGS = 256

# --- Path simplification (Task 4) ---
# Douglas-Peucker tolerance, in mm (points are simplified after the
# user-unit -> mm scale has already been applied), well under machine
# accuracy so simplification cannot visibly change cut geometry.
SIMPLIFY_TOLERANCE_MM = 0.02


@dataclass(frozen=True)
class Pt:
    x: float
    y: float
    cmd: str  # 'M' or 'L'


@dataclass(frozen=True)
class Mat:
    """
    SVG 2D affine matrix:
      [ a c e ]
      [ b d f ]
      [ 0 0 1 ]
    """
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def apply(self, x: float, y: float) -> Tuple[float, float]:
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def mul(self, other: "Mat") -> "Mat":
        # self * other
        return Mat(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            e=self.a * other.e + self.c * other.f + self.e,
            f=self.b * other.e + self.d * other.f + self.f,
        )


def _parse_transform(transform: Optional[str]) -> Mat:
    """
    Parse a subset of SVG transforms: matrix, translate, scale, rotate.
    Order matters: SVG applies them left-to-right.
    """
    if not transform:
        return Mat()
    s = str(transform).strip()
    if not s:
        return Mat()

    # tokenize like: translate(1,2) scale(2) rotate(45,10,10) matrix(...)
    pieces = re.findall(r"([a-zA-Z]+)\s*\(([^)]*)\)", s)
    m = Mat()
    for name, args_str in pieces:
        name = name.strip().lower()
        nums = _parse_floats(args_str)
        if name == "matrix" and len(nums) >= 6:
            t = Mat(nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])
            m = m.mul(t)
        elif name == "translate" and len(nums) >= 1:
            tx = nums[0]
            ty = nums[1] if len(nums) >= 2 else 0.0
            t = Mat(1, 0, 0, 1, tx, ty)
            m = m.mul(t)
        elif name == "scale" and len(nums) >= 1:
            sx = nums[0]
            sy = nums[1] if len(nums) >= 2 else sx
            t = Mat(sx, 0, 0, sy, 0, 0)
            m = m.mul(t)
        elif name == "rotate" and len(nums) >= 1:
            ang = math.radians(nums[0])
            ca = math.cos(ang)
            sa = math.sin(ang)
            r = Mat(ca, sa, -sa, ca, 0, 0)
            if len(nums) >= 3:
                cx, cy = nums[1], nums[2]
                # T(cx,cy) * R * T(-cx,-cy)
                m = m.mul(Mat(1, 0, 0, 1, cx, cy)).mul(r).mul(Mat(1, 0, 0, 1, -cx, -cy))
            else:
                m = m.mul(r)
        # ignore skewX/skewY/unknown for now
    return m


def _local_name(el) -> str:
    try:
        return etree.QName(el).localname
    except Exception:
        # Fallback: strip namespace manually
        tag = getattr(el, "tag", "") or ""
        return tag.rsplit("}", 1)[-1]


def _parse_number_and_unit(s: Optional[str]) -> Tuple[Optional[float], str]:
    """
    Parse e.g. "210mm", "800px", "8.5in", "100" into (value, unit).
    Returns (None, "") if missing/invalid.
    """
    if not s:
        return None, ""
    s = str(s).strip()
    m = re.match(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z%]*)\s*$", s)
    if not m:
        return None, ""
    val = float(m.group(1))
    unit = (m.group(2) or "").strip().lower()
    return val, unit


def _to_mm(value: float, unit: str) -> float:
    unit = (unit or "").lower()
    if unit in ("mm", ""):
        return float(value)
    if unit == "cm":
        return float(value) * 10.0
    if unit in ("in", "inch"):
        return float(value) * MM_PER_INCH
    if unit == "px":
        return float(value) * MM_PER_PX
    # Unknown units: assume px (common for SVG)
    return float(value) * MM_PER_PX


def _get_svg_dimensions_and_scale(svg_root) -> Tuple[float, float, float, float]:
    """
    Returns (svg_w_mm, svg_h_mm, scale_x, scale_y).
    scale_x/scale_y convert SVG user units (typically viewBox units) -> mm.
    """
    w_attr = svg_root.get("width")
    h_attr = svg_root.get("height")
    vb_attr = svg_root.get("viewBox") or svg_root.get("viewbox")

    w_val, w_unit = _parse_number_and_unit(w_attr)
    h_val, h_unit = _parse_number_and_unit(h_attr)

    view_w = view_h = None
    if vb_attr:
        parts = re.split(r"[\s,]+", vb_attr.strip())
        if len(parts) == 4:
            try:
                # minX, minY ignored for now (common case is 0 0 w h)
                view_w = float(parts[2])
                view_h = float(parts[3])
            except Exception:
                view_w = view_h = None

    # Compute output dimensions in mm
    if w_val is not None and h_val is not None:
        svg_w_mm = _to_mm(w_val, w_unit)
        svg_h_mm = _to_mm(h_val, h_unit)
    elif view_w is not None and view_h is not None:
        # No explicit width/height: assume viewBox units are px at 96 DPI
        svg_w_mm = view_w * MM_PER_PX
        svg_h_mm = view_h * MM_PER_PX
    else:
        # Worst-case fallback: OKU bed size
        svg_w_mm = BED_W_MM
        svg_h_mm = BED_H_MM

    # Compute scaling from user units -> mm
    if view_w is not None and view_h is not None and view_w != 0 and view_h != 0:
        scale_x = svg_w_mm / view_w
        scale_y = svg_h_mm / view_h
    else:
        # Assume user units already in mm (or close enough)
        scale_x = 1.0
        scale_y = 1.0

    # Guard against nonsense
    if not (svg_w_mm > 0):
        svg_w_mm = BED_W_MM
    if not (svg_h_mm > 0):
        svg_h_mm = BED_H_MM

    return svg_w_mm, svg_h_mm, scale_x, scale_y


def _extract_path_ds(svg_root) -> List[str]:
    """
    Backward-compat helper kept for older usage.
    """
    ds: List[str] = []
    for el, _mat in _extract_drawables(svg_root):
        if _local_name(el) == "path":
            d = el.get("d")
            if d and str(d).strip():
                ds.append(str(d))
    return ds


def _rect_to_path_d(el) -> Optional[str]:
    # Minimal: ignore rounded corners (rx/ry) for now.
    x = float(el.get("x") or 0.0)
    y = float(el.get("y") or 0.0)
    w = float(el.get("width") or 0.0)
    h = float(el.get("height") or 0.0)
    if w <= 0 or h <= 0:
        return None
    x2 = x + w
    y2 = y + h
    return f"M {x} {y} L {x2} {y} L {x2} {y2} L {x} {y2} Z"


def _line_to_path_d(el) -> Optional[str]:
    x1 = float(el.get("x1") or 0.0)
    y1 = float(el.get("y1") or 0.0)
    x2 = float(el.get("x2") or 0.0)
    y2 = float(el.get("y2") or 0.0)
    return f"M {x1} {y1} L {x2} {y2}"


def _poly_to_path_d(el) -> Optional[str]:
    pts = (el.get("points") or "").strip()
    if not pts:
        return None
    nums = _parse_floats(pts.replace(",", " "))
    if len(nums) < 4:
        return None
    pairs = list(zip(nums[0::2], nums[1::2]))
    if not pairs:
        return None
    parts = [f"M {pairs[0][0]} {pairs[0][1]}"]
    for x, y in pairs[1:]:
        parts.append(f"L {x} {y}")
    if _local_name(el) == "polygon":
        parts.append("Z")
    return " ".join(parts)


def _circle_ellipse_to_path_d(el) -> Optional[str]:
    # Approximate with polyline (32 segments)
    name = _local_name(el)
    if name == "circle":
        cx = float(el.get("cx") or 0.0)
        cy = float(el.get("cy") or 0.0)
        r = float(el.get("r") or 0.0)
        rx = ry = r
    else:
        cx = float(el.get("cx") or 0.0)
        cy = float(el.get("cy") or 0.0)
        rx = float(el.get("rx") or 0.0)
        ry = float(el.get("ry") or 0.0)
    if rx <= 0 or ry <= 0:
        return None
    segs = 32
    pts = []
    for i in range(segs + 1):
        t = (i / segs) * 2 * math.pi
        x = cx + rx * math.cos(t)
        y = cy + ry * math.sin(t)
        pts.append((x, y))
    d = f"M {pts[0][0]} {pts[0][1]} " + " ".join(f"L {x} {y}" for x, y in pts[1:]) + " Z"
    return d


def _extract_drawables(svg_root) -> List[Tuple[object, Mat]]:
    """
    Walk the SVG tree and return drawable elements with their accumulated transform matrix.
    """
    out: List[Tuple[object, Mat]] = []

    def walk(el, parent_mat: Mat):
        this_mat = parent_mat.mul(_parse_transform(el.get("transform")))
        lname = _local_name(el)
        if lname in ("path", "rect", "circle", "ellipse", "line", "polyline", "polygon"):
            out.append((el, this_mat))
        for child in list(el):
            walk(child, this_mat)

    walk(svg_root, Mat())
    return out


_OP_RE = re.compile(r"[a-df-zA-DF-Z][^a-df-zA-DF-Z]*")  # excludes e/E for scientific notation safety


def _split_ops(d: str) -> List[str]:
    return _OP_RE.findall(d or "")


def _parse_floats(s: str) -> List[float]:
    if not s:
        return []
    parts = re.split(r"[\s,]+", s.strip())
    out = []
    for p in parts:
        if not p:
            continue
        try:
            out.append(float(p))
        except Exception:
            continue
    return out


def _bezier_point(p0, p1, p2, p3, t: float) -> Tuple[float, float]:
    mt = 1.0 - t
    mt2 = mt * mt
    mt3 = mt2 * mt
    t2 = t * t
    t3 = t2 * t
    x = mt3 * p0[0] + 3 * mt2 * t * p1[0] + 3 * mt * t2 * p2[0] + t3 * p3[0]
    y = mt3 * p0[1] + 3 * mt2 * t * p1[1] + 3 * mt * t2 * p2[1] + t3 * p3[1]
    return x, y


def _dist2(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _cubic_seg_count(p0, p1, p2, p3, tol: float) -> int:
    """
    Estimate the number of line segments needed to flatten a cubic Bezier to
    within `tol` (chord error), from the control-polygon length vs. how much
    the polygon "bends" away from the straight chord.

    Heuristic (classic curve-flattening estimate): segs ~ sqrt(L * bend / (8 * tol)),
    where L is the control-polygon length and `bend` is how much longer the
    polygon is than the direct chord (a proxy for curvature/deviation). A
    straight or near-straight curve needs very few segments; a long, sharply
    bent one needs more.
    """
    poly_len = _dist2(p0, p1) + _dist2(p1, p2) + _dist2(p2, p3)
    if poly_len <= 1e-9:
        return _MIN_BEZIER_SEGS
    chord_len = _dist2(p0, p3)
    bend = max(0.0, poly_len - chord_len)
    segs = int(math.ceil(math.sqrt((poly_len * bend) / (8.0 * max(tol, 1e-9))))) + 1
    return max(_MIN_BEZIER_SEGS, min(_MAX_BEZIER_SEGS, segs))


def _quad_seg_count(p0, p1, p2, tol: float) -> int:
    """Same heuristic as `_cubic_seg_count`, for a quadratic Bezier's 3-point hull."""
    poly_len = _dist2(p0, p1) + _dist2(p1, p2)
    if poly_len <= 1e-9:
        return _MIN_BEZIER_SEGS
    chord_len = _dist2(p0, p2)
    bend = max(0.0, poly_len - chord_len)
    segs = int(math.ceil(math.sqrt((poly_len * bend) / (8.0 * max(tol, 1e-9))))) + 1
    return max(_MIN_BEZIER_SEGS, min(_MAX_BEZIER_SEGS, segs))


def _vector_angle(ux: float, uy: float, vx: float, vy: float) -> float:
    # angle between vectors u and v, signed by cross product
    dot = ux * vx + uy * vy
    det = ux * vy - uy * vx
    return math.atan2(det, dot)


def _arc_to_points(
    x1: float,
    y1: float,
    rx: float,
    ry: float,
    phi_deg: float,
    large_arc_flag: int,
    sweep_flag: int,
    x2: float,
    y2: float,
) -> List[Tuple[float, float]]:
    """
    Convert an SVG elliptical arc (endpoint form) into a list of points on the arc
    (excluding the start point, including the end point).

    Implements the algorithm from the SVG spec (endpoint to center parameterization).
    """
    # Handle degenerate cases
    if rx == 0 or ry == 0:
        return [(x2, y2)]

    rx = abs(rx)
    ry = abs(ry)
    phi = math.radians(phi_deg % 360.0)
    cosphi = math.cos(phi)
    sinphi = math.sin(phi)

    # Step 1: compute (x1', y1')
    dx2 = (x1 - x2) / 2.0
    dy2 = (y1 - y2) / 2.0
    x1p = cosphi * dx2 + sinphi * dy2
    y1p = -sinphi * dx2 + cosphi * dy2

    # Step 2: ensure radii are large enough
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        s = math.sqrt(lam)
        rx *= s
        ry *= s

    # Step 3: compute (cx', cy')
    rx2 = rx * rx
    ry2 = ry * ry
    x1p2 = x1p * x1p
    y1p2 = y1p * y1p

    # Protect against tiny negative due to float
    num = max(0.0, rx2 * ry2 - rx2 * y1p2 - ry2 * x1p2)
    den = max(1e-18, rx2 * y1p2 + ry2 * x1p2)
    coef = math.sqrt(num / den)
    if int(large_arc_flag) == int(sweep_flag):
        coef = -coef
    cxp = coef * (rx * y1p) / ry
    cyp = coef * (-ry * x1p) / rx

    # Step 4: compute (cx, cy)
    cx = cosphi * cxp - sinphi * cyp + (x1 + x2) / 2.0
    cy = sinphi * cxp + cosphi * cyp + (y1 + y2) / 2.0

    # Step 5: compute start/end angles
    ux = (x1p - cxp) / rx
    uy = (y1p - cyp) / ry
    vx = (-x1p - cxp) / rx
    vy = (-y1p - cyp) / ry

    theta1 = _vector_angle(1.0, 0.0, ux, uy)
    dtheta = _vector_angle(ux, uy, vx, vy)

    if not sweep_flag and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep_flag and dtheta < 0:
        dtheta += 2 * math.pi

    # Choose number of segments by angular span (min 6, max 120)
    segs = int(max(6, min(120, math.ceil(abs(dtheta) / (math.pi / 18.0)))))  # ~10° per segment

    pts: List[Tuple[float, float]] = []
    for i in range(1, segs + 1):
        t = theta1 + (dtheta * i) / segs
        ct = math.cos(t)
        st = math.sin(t)
        # ellipse point in rotated coords back to original
        x = cx + (rx * ct * cosphi - ry * st * sinphi)
        y = cy + (rx * ct * sinphi + ry * st * cosphi)
        pts.append((x, y))
    # Ensure exact end
    if pts:
        pts[-1] = (x2, y2)
    else:
        pts = [(x2, y2)]
    return pts


def _quad_bezier_point(p0, p1, p2, t: float) -> Tuple[float, float]:
    mt = 1.0 - t
    x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
    y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
    return x, y


def _path_to_points(d: str, scale_x: float = 1.0, scale_y: float = 1.0) -> List[Pt]:
    """
    Convert SVG path 'd' to a list of Pt(x,y,cmd) in *user units* (pre-scaling).
    Supports: M, L, H, V, Z, C, S (cubic bezier + smooth variant), Q, T (quadratic
    bezier + smooth variant), A (elliptical arc), all approximated by line segments.

    An unrecognized command raises ValueError rather than being silently dropped,
    since silently ignoring a command both drops geometry AND fails to advance the
    current point, displacing every subsequent command in the path.

    `scale_x`/`scale_y` are the caller's user-unit -> mm scale factors (the same
    ones later multiplied into the returned points' coordinates). They are used
    ONLY to convert `CURVE_TOLERANCE_MM` (a physical mm tolerance) into an
    equivalent tolerance in this function's *user-unit* coordinate space, so
    Bezier flattening actually targets ~CURVE_TOLERANCE_MM of chord error on
    the machine, not on an arbitrary pre-scale unit. We divide by
    max(scale_x, scale_y) (not an average) so that on non-uniform scale the
    tighter (larger-scale) axis is still guaranteed within tolerance -- this
    can only make curves on the other axis *more* accurate than strictly
    necessary, never less.

    Caveat: if this path is later run through an additional transform matrix
    (a `mat` from a containing <g transform=...>, applied by the caller after
    this function returns) that itself scales geometry, that extra scaling is
    NOT accounted for here -- the effective mm tolerance for such paths may
    differ from CURVE_TOLERANCE_MM by the transform's own scale factor. This
    is a known, documented simplification: composing an arbitrary transform's
    scale component was judged out of scope for this pass.
    """
    if scale_x <= 0 or not math.isfinite(scale_x):
        scale_x = 1.0
    if scale_y <= 0 or not math.isfinite(scale_y):
        scale_y = 1.0
    curve_tol = CURVE_TOLERANCE_MM / max(scale_x, scale_y)

    ops = _split_ops(d)
    pts: List[Pt] = []
    cx = cy = 0.0
    sx = sy = 0.0  # start of subpath

    # Track the previous command (uppercase) and its trailing control point,
    # needed to compute reflected control points for S/s and T/t.
    prev_cmd: Optional[str] = None
    prev_ctrl: Optional[Tuple[float, float]] = None

    for op in ops:
        if not op:
            continue
        t = op[0]
        rel = t.islower()
        T = t.upper()
        args = _parse_floats(op[1:])

        if T == "M":
            # First pair is Move; additional pairs are implicit LineTo
            if len(args) >= 2:
                x = args[0]
                y = args[1]
                cx = cx + x if rel else x
                cy = cy + y if rel else y
                sx, sy = cx, cy
                pts.append(Pt(cx, cy, "M"))
                # implicit L for remaining pairs
                i = 2
                while i + 1 < len(args):
                    x = args[i]
                    y = args[i + 1]
                    cx = cx + x if rel else x
                    cy = cy + y if rel else y
                    pts.append(Pt(cx, cy, "L"))
                    i += 2
            prev_cmd, prev_ctrl = T, None
            continue

        if T == "L":
            i = 0
            while i + 1 < len(args):
                x = args[i]
                y = args[i + 1]
                cx = cx + x if rel else x
                cy = cy + y if rel else y
                pts.append(Pt(cx, cy, "L"))
                i += 2
            prev_cmd, prev_ctrl = T, None
            continue

        if T == "H":
            for x in args:
                cx = cx + x if rel else x
                pts.append(Pt(cx, cy, "L"))
            prev_cmd, prev_ctrl = T, None
            continue

        if T == "V":
            for y in args:
                cy = cy + y if rel else y
                pts.append(Pt(cx, cy, "L"))
            prev_cmd, prev_ctrl = T, None
            continue

        if T == "Z":
            # close path
            cx, cy = sx, sy
            pts.append(Pt(cx, cy, "L"))
            prev_cmd, prev_ctrl = T, None
            continue

        if T == "C":
            # Cubic bezier: can have multiple segments (6*n)
            i = 0
            while i + 5 < len(args):
                x1, y1, x2, y2, x3, y3 = args[i : i + 6]
                p0 = (cx, cy)
                if rel:
                    p1 = (cx + x1, cy + y1)
                    p2 = (cx + x2, cy + y2)
                    p3 = (cx + x3, cy + y3)
                else:
                    p1 = (x1, y1)
                    p2 = (x2, y2)
                    p3 = (x3, y3)

                segs = _cubic_seg_count(p0, p1, p2, p3, curve_tol)
                for k in range(1, segs + 1):
                    tt = k / segs
                    bx, by = _bezier_point(p0, p1, p2, p3, tt)
                    pts.append(Pt(bx, by, "L"))
                cx, cy = p3
                prev_ctrl = p2
                i += 6
            prev_cmd = T
            continue

        if T == "S":
            # Smooth cubic bezier: reflect previous C/S second control point about
            # the current point to get this segment's first control point.
            i = 0
            while i + 3 < len(args):
                x2, y2, x3, y3 = args[i : i + 4]
                p0 = (cx, cy)
                if prev_cmd in ("C", "S") and prev_ctrl is not None:
                    p1 = (2 * cx - prev_ctrl[0], 2 * cy - prev_ctrl[1])
                else:
                    p1 = (cx, cy)
                if rel:
                    p2 = (cx + x2, cy + y2)
                    p3 = (cx + x3, cy + y3)
                else:
                    p2 = (x2, y2)
                    p3 = (x3, y3)

                segs = _cubic_seg_count(p0, p1, p2, p3, curve_tol)
                for k in range(1, segs + 1):
                    tt = k / segs
                    bx, by = _bezier_point(p0, p1, p2, p3, tt)
                    pts.append(Pt(bx, by, "L"))
                cx, cy = p3
                prev_ctrl = p2
                prev_cmd = "S"
                i += 4
            continue

        if T == "Q":
            # Quadratic bezier, elevated to cubic form for reuse of _bezier_point.
            i = 0
            while i + 3 < len(args):
                x1, y1, x2, y2 = args[i : i + 4]
                p0 = (cx, cy)
                if rel:
                    p1 = (cx + x1, cy + y1)
                    p2 = (cx + x2, cy + y2)
                else:
                    p1 = (x1, y1)
                    p2 = (x2, y2)

                segs = _quad_seg_count(p0, p1, p2, curve_tol)
                for k in range(1, segs + 1):
                    tt = k / segs
                    bx, by = _quad_bezier_point(p0, p1, p2, tt)
                    pts.append(Pt(bx, by, "L"))
                cx, cy = p2
                prev_ctrl = p1
                prev_cmd = "Q"
                i += 4
            continue

        if T == "T":
            # Smooth quadratic: reflect previous Q/T control point about the
            # current point; if no such previous command, control point == current point.
            i = 0
            while i + 1 < len(args):
                x2, y2 = args[i], args[i + 1]
                p0 = (cx, cy)
                if prev_cmd in ("Q", "T") and prev_ctrl is not None:
                    p1 = (2 * cx - prev_ctrl[0], 2 * cy - prev_ctrl[1])
                else:
                    p1 = (cx, cy)
                if rel:
                    p2 = (cx + x2, cy + y2)
                else:
                    p2 = (x2, y2)

                segs = _quad_seg_count(p0, p1, p2, curve_tol)
                for k in range(1, segs + 1):
                    tt = k / segs
                    bx, by = _quad_bezier_point(p0, p1, p2, tt)
                    pts.append(Pt(bx, by, "L"))
                cx, cy = p2
                prev_ctrl = p1
                prev_cmd = "T"
                i += 2
            continue

        if T == "A":
            # Elliptical arc: rx ry xAxisRotation largeArcFlag sweepFlag x y (repeat)
            i = 0
            while i + 6 < len(args):
                rx, ry = args[i], args[i + 1]
                phi = args[i + 2]
                laf = int(args[i + 3])
                sf = int(args[i + 4])
                x = args[i + 5]
                y = args[i + 6]
                x2 = cx + x if rel else x
                y2 = cy + y if rel else y

                arc_pts = _arc_to_points(cx, cy, rx, ry, phi, laf, sf, x2, y2)
                for ax, ay in arc_pts:
                    pts.append(Pt(ax, ay, "L"))
                cx, cy = x2, y2
                i += 7
            prev_cmd, prev_ctrl = T, None
            continue

        # A genuinely unknown command must not be silently ignored: dropping it
        # both loses geometry and fails to advance (cx, cy), displacing every
        # subsequent command in the path.
        raise ValueError(f"Unsupported SVG path command: {t!r} in path data {d!r}")

    return pts


def _apply_mat_to_points(pts: List[Pt], mat: Mat) -> List[Pt]:
    if not pts:
        return pts
    out: List[Pt] = []
    for p in pts:
        x2, y2 = mat.apply(p.x, p.y)
        out.append(Pt(x2, y2, p.cmd))
    return out


def _fmt(n: float) -> str:
    if n is None or (isinstance(n, float) and (math.isnan(n) or math.isinf(n))):
        return "0"
    v = round(float(n), 4)
    s = f"{v:.4f}"
    s = re.sub(r"\.?0+$", "", s)
    return s if s else "0"


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return math.hypot(dx, dy)


# ---------------------------------------------------------------------------
# Task 1/2: toolpath path-order optimization
# ---------------------------------------------------------------------------


def _reverse_path(pts: List[Pt]) -> List[Pt]:
    """
    Reverse a path's point order in place-semantics (returns a new list),
    rebuilding `cmd` so the new first point is 'M' (rapid target) and every
    following point is 'L' (cut). This is geometry-preserving: the exact same
    set of segments gets drawn, just walked from the opposite end. The `cmd`
    field must be rebuilt rather than just flipping the list, since the
    original first point ('M') is now in the interior (must become 'L') and
    the original last point is now first (must become 'M').
    """
    if not pts:
        return pts
    rev = list(reversed(pts))
    out = [Pt(rev[0].x, rev[0].y, "M")]
    for p in rev[1:]:
        out.append(Pt(p.x, p.y, "L"))
    return out


def _path_endpoints(pts: List[Pt]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    if not pts:
        return (0.0, 0.0), (0.0, 0.0)
    return (pts[0].x, pts[0].y), (pts[-1].x, pts[-1].y)


def _two_opt_improve(
    tour: List[List[Pt]], start_point: Tuple[float, float]
) -> List[List[Pt]]:
    """
    Bounded 2-opt improvement pass over an already-ordered (and already
    reversal-decided) tour of paths. Classic 2-opt for a directed
    Hamiltonian path: removing two edges and reconnecting requires reversing
    the *order* of the paths between them AND flipping each path's own
    direction (since the sub-tour is now walked backwards).

    Bounded by TWO_OPT_MAX_PASSES full sweeps and TWO_OPT_MAX_SWAPS total
    accepted swaps, so a pathological or oscillating case cannot hang.
    """
    n = len(tour)
    if n < 3:
        return tour

    entries: List[Tuple[float, float]] = []
    exits: List[Tuple[float, float]] = []
    for pts in tour:
        e0, e1 = _path_endpoints(pts)
        entries.append(e0)
        exits.append(e1)

    total_swaps = 0
    for _pass in range(TWO_OPT_MAX_PASSES):
        improved = False
        for i in range(n - 1):
            prev_exit = start_point if i == 0 else exits[i - 1]
            for j in range(i + 1, n):
                next_entry = entries[j + 1] if j + 1 < n else None

                old_cost = _dist(prev_exit, entries[i])
                new_cost = _dist(prev_exit, exits[j])
                if next_entry is not None:
                    old_cost += _dist(exits[j], next_entry)
                    new_cost += _dist(entries[i], next_entry)

                if new_cost + 1e-9 < old_cost:
                    seg_entries = entries[i : j + 1]
                    seg_exits = exits[i : j + 1]
                    entries[i : j + 1] = list(reversed(seg_exits))
                    exits[i : j + 1] = list(reversed(seg_entries))
                    tour[i : j + 1] = [_reverse_path(p) for p in reversed(tour[i : j + 1])]

                    improved = True
                    total_swaps += 1
                    if total_swaps >= TWO_OPT_MAX_SWAPS:
                        return tour
        if not improved:
            break
    return tour


def _optimize_path_order(
    paths: List[List[Pt]], start_point: Tuple[float, float] = (0.0, 0.0)
) -> List[List[Pt]]:
    """
    Reorder `paths` (a list of point-lists sharing one coordinate space, e.g.
    one job/color batch) to reduce total rapid-move travel: greedy
    nearest-neighbour with optional path reversal, followed by a bounded
    2-opt improvement pass.

    - Greedy nearest-neighbour: repeatedly pick the unvisited path whose
      entry point is closest to the current head position; the head then
      moves to that path's exit point.
    - Reversal: for each candidate, both endpoints are considered as the
      possible entry; whichever is closer wins, reversing the path's point
      list (and rebuilding `cmd`) if its far end is nearer.
    - Closed contours (first ~= last point) are NOT seam-rotated: rotating a
      closed contour's start point is a real extra win, but it also moves
      where the lead-in/out burn mark lands on the cut edge, which is a cut
      *quality* tradeoff, not a pure toolpath-time one. Skipped deliberately
      here rather than risk that regression silently; see report.

    IMPORTANT: callers must invoke this once per job/color batch, and never
    on a list merged across batches -- job order is user-controlled and
    reordering across batches would silently violate user intent.
    """
    n = len(paths)
    if n <= 1:
        return list(paths)

    endpoints = [_path_endpoints(pts) for pts in paths]
    visited = [False] * n
    ordered: List[List[Pt]] = []
    head = start_point

    for _ in range(n):
        best_idx = -1
        best_dist = math.inf
        best_rev = False
        for idx in range(n):
            if visited[idx]:
                continue
            entry, exit_ = endpoints[idx]
            d_fwd = _dist(head, entry)
            d_rev = _dist(head, exit_)
            if d_rev < d_fwd:
                cand_d, cand_rev = d_rev, True
            else:
                cand_d, cand_rev = d_fwd, False
            if cand_d < best_dist:
                best_dist = cand_d
                best_idx = idx
                best_rev = cand_rev

        pts = paths[best_idx]
        if best_rev:
            pts = _reverse_path(pts)
            head = endpoints[best_idx][0]
        else:
            head = endpoints[best_idx][1]
        ordered.append(pts)
        visited[best_idx] = True

    if n <= TWO_OPT_MAX_PATHS:
        ordered = _two_opt_improve(ordered, start_point)

    return ordered


# ---------------------------------------------------------------------------
# Task 4: path simplification (Douglas-Peucker)
# ---------------------------------------------------------------------------


def _point_segment_dist(
    p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]
) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return _dist(p, a)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj = (ax + t * dx, ay + t * dy)
    return _dist(p, proj)


def _douglas_peucker(
    points: List[Tuple[float, float]], tolerance: float
) -> List[Tuple[float, float]]:
    """
    Iterative (stack-based, not recursive) Douglas-Peucker polyline
    simplification. Iterative to avoid Python's recursion limit on paths with
    many collinear-violating points (worst case depth == point count).
    Always keeps the first and last point exactly.
    """
    n = len(points)
    if n < 3:
        return list(points)

    keep = [False] * n
    keep[0] = True
    keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start_idx, end_idx = stack.pop()
        if end_idx <= start_idx + 1:
            continue
        a = points[start_idx]
        b = points[end_idx]
        max_dist = -1.0
        split_idx = -1
        for i in range(start_idx + 1, end_idx):
            d = _point_segment_dist(points[i], a, b)
            if d > max_dist:
                max_dist = d
                split_idx = i
        if max_dist > tolerance:
            keep[split_idx] = True
            stack.append((start_idx, split_idx))
            stack.append((split_idx, end_idx))
    return [points[i] for i in range(n) if keep[i]]


def _simplify_pts(pts: List[Pt], tolerance: float) -> List[Pt]:
    """
    Douglas-Peucker-simplify a flattened/transformed point list, in whatever
    coordinate space it's already in (callers apply this once points are in
    mm, so `tolerance` means mm of chord error).

    A single parsed <path> element's `d` can itself contain multiple
    subpaths (multiple 'M' commands); simplification must not merge points
    across such a boundary, so this splits on 'M' first and simplifies each
    subpath independently, which also guarantees each subpath's first and
    last point survive exactly.
    """
    if len(pts) < 3:
        return pts

    subpaths: List[List[Pt]] = []
    cur: List[Pt] = []
    for p in pts:
        if p.cmd == "M" and cur:
            subpaths.append(cur)
            cur = []
        cur.append(p)
    if cur:
        subpaths.append(cur)

    out: List[Pt] = []
    for sp in subpaths:
        if len(sp) < 3:
            out.extend(sp)
            continue
        coords = [(p.x, p.y) for p in sp]
        simplified = _douglas_peucker(coords, tolerance)
        out.append(Pt(simplified[0][0], simplified[0][1], "M"))
        for x, y in simplified[1:]:
            out.append(Pt(x, y, "L"))
    return out


def _make_meta_header(
    bounds: Tuple[float, float, float, float],
    estimated_minutes: float,
    speed: int,
    power_pct: float,
    passes: int,
    thumb_w: int,
    thumb_h: int,
    thumb_rows_hex: List[str],
) -> List[str]:
    """
    Return metadata block as a list of strings that already include their trailing newlines,
    matching the original NomadTech scripts' behavior (they append strings with '\n').
    """
    minx, maxx, miny, maxy = bounds
    w = max(0.0, maxx - minx) if all(map(math.isfinite, [minx, maxx])) else 0.0
    h = max(0.0, maxy - miny) if all(map(math.isfinite, [miny, maxy])) else 0.0
    safe_x = minx if math.isfinite(minx) else 0.0
    safe_y = miny if math.isfinite(miny) else 0.0

    meta: List[str] = []
    meta.append(";$M Meta untilchar 000000\n")  # placeholder updated below
    meta.append(f";$M Frame X{w:.2f} Y{h:.2f}\n")
    meta.append(f";$M Pos X{safe_x:.2f} Y{safe_y:.2f}\n")
    meta.append(";$M NumOps 1\n")
    meta.append(";$M Op 0\n")
    meta.append(";$M Type Vector\n")
    meta.append(f";$M Speed {int(speed)}\n")
    meta.append(f";$M Power {float(power_pct):.1f}\n")
    meta.append(f";$M Rep {int(passes)}\n")
    meta.append(f";$M Time {int(math.ceil(max(0.0, estimated_minutes)))}\n")

    # Thumbnail block (vector script generates this; required for preview)
    tw = max(1, int(thumb_w))
    th = max(1, int(thumb_h))
    meta.append(f";$M Thumb start X{tw} Y{th}\n")
    for row in thumb_rows_hex:
        meta.append(f";$MT {row}\n")
    meta.append(";$M Thumb end\n\n")

    meta_len = sum(len(s) for s in meta)
    meta[0] = f";$M Meta untilchar {meta_len:06d}\n"
    return meta


def _make_meta_header_raster(
    bounds: Tuple[float, float, float, float],
    estimated_minutes: float,
    speed: int,
    power_pct: float,
    passes: int,
    thumb_w: int,
    thumb_h: int,
    thumb_rows_hex: List[str],
    margin: float = 7.18,
) -> List[str]:
    """
    Raster metadata block (includes Margin + Type Raster).
    Returns a list of strings including trailing newlines, like NomadTech scripts.
    """
    minx, maxx, miny, maxy = bounds
    w = max(0.0, maxx - minx) if all(map(math.isfinite, [minx, maxx])) else 0.0
    h = max(0.0, maxy - miny) if all(map(math.isfinite, [miny, maxy])) else 0.0
    safe_x = minx if math.isfinite(minx) else 0.0
    safe_y = miny if math.isfinite(miny) else 0.0

    meta: List[str] = []
    meta.append(";$M Meta untilchar 000000\n")
    meta.append(f";$M Frame X{w:.2f} Y{h:.2f}\n")
    meta.append(f";$M Pos X{safe_x:.2f} Y{safe_y:.2f}\n")
    meta.append(f";$M Margin {float(margin):.2f}\n")
    meta.append(";$M NumOps 1\n")
    meta.append(";$M Op 0\n")
    meta.append(";$M Type Raster\n")
    meta.append(f";$M Speed {int(speed)}\n")
    meta.append(f";$M Power {float(power_pct):.1f}\n")
    meta.append(f";$M Rep {int(passes)}\n")
    meta.append(f";$M Time {int(math.ceil(max(0.0, estimated_minutes)))}\n")

    tw = max(1, int(thumb_w))
    th = max(1, int(thumb_h))
    meta.append(f";$M Thumb start X{tw} Y{th}\n")
    for row in thumb_rows_hex:
        meta.append(f";$MT {row}\n")
    meta.append(";$M Thumb end\n\n")

    meta_len = sum(len(s) for s in meta)
    meta[0] = f";$M Meta untilchar {meta_len:06d}\n"
    return meta


def _segments_from_paths(all_paths: List[List[Pt]], svg_h_mm: float, offset_x: float, offset_y: float) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    segs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for pts in all_paths:
        prev: Optional[Tuple[float, float]] = None
        for p in pts:
            mx = p.x + offset_x
            my = (svg_h_mm - p.y) + offset_y
            if p.cmd == "M":
                prev = (mx, my)
                continue
            if p.cmd == "L" and prev is not None:
                cur = (mx, my)
                # ignore ultra-short segments
                if abs(cur[0] - prev[0]) >= ZERO_MOVE_THRESHOLD or abs(cur[1] - prev[1]) >= ZERO_MOVE_THRESHOLD:
                    segs.append((prev, cur))
                prev = cur
    return segs


def _make_thumbnail_rows(
    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]],
    bounds: Tuple[float, float, float, float],
    max_w: int = THUMB_MAX_W,
    max_h: int = THUMB_MAX_H,
) -> Tuple[int, int, List[str]]:
    """
    Generate thumbnail rows as hex strings ('%02X' per pixel) like NomadTech.
    Fallback: returns a blank thumbnail if Pillow isn't available.
    """
    minx, maxx, miny, maxy = bounds
    width = max(0.0, maxx - minx)
    height = max(0.0, maxy - miny)

    # If we have no geometry, return a tiny blank thumbnail
    if width <= 0 or height <= 0 or not segments:
        tw, th = 1, 1
        return tw, th, ["FF"]

    # Determine thumbnail size preserving aspect ratio (like PIL thumbnail)
    scale = min(float(max_w) / width, float(max_h) / height)
    tw = max(1, int(round(width * scale)))
    th = max(1, int(round(height * scale)))

    try:
        from PIL import Image, ImageDraw  # type: ignore
        img = Image.new("L", (tw, th), 255)  # white background
        draw = ImageDraw.Draw(img)

        def to_px(pt: Tuple[float, float]) -> Tuple[float, float]:
            x, y = pt
            # map bounds->image, and flip Y for image coordinates (top-left origin)
            px = (x - minx) * scale
            py = (maxy - y) * scale
            return (px, py)

        for a, b in segments:
            draw.line([to_px(a), to_px(b)], fill=0, width=1)

        pixels = list(img.getdata())
        # Build rows of hex bytes (two hex chars per pixel)
        rows: List[str] = []
        for r in range(th):
            row = pixels[r * tw : (r + 1) * tw]
            rows.append("".join(f"{v:02X}" for v in row))
        return tw, th, rows
    except Exception:
        # Pillow missing or failed: blank preview (white)
        rows = ["FF" * tw for _ in range(th)]
        return tw, th, rows


def _make_thumbnail_rows_from_image(im_l, *, contrast: float = 1.0) -> Tuple[int, int, List[str]]:
    """
    NomadTech-style thumbnail: resize to max 225x159, grayscale, emit rows of %02X bytes.
    """
    try:
        from PIL import Image, ImageEnhance  # type: ignore
        img = im_l.copy()
        img.thumbnail((THUMB_MAX_W, THUMB_MAX_H))
        img = img.convert('L')
        if contrast and float(contrast) != 1.0:
            # Optional: boost contrast so thin features show up
            try:
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(float(contrast))
            except Exception:
                pass
        w, h = img.size
        px = list(img.getdata())
        rows = []
        for r in range(h):
            row = px[r * w : (r + 1) * w]
            rows.append("".join(f"{v:02X}" for v in row))
        return w, h, rows
    except Exception:
        return 1, 1, ["FF"]


def _fmt3(n: float) -> str:
    # Raster script uses 3 decimals
    return f"{float(n):.3f}"


def _decode_image_data(image_base64: str):
    """
    Accepts a raw base64 string or a data URL: data:image/png;base64,...
    Returns a Pillow Image.
    """
    from PIL import Image  # type: ignore
    s = (image_base64 or "").strip()
    if not s:
        raise ValueError("image_base64 is required")
    if s.startswith("data:"):
        comma = s.find(",")
        if comma == -1:
            raise ValueError("Invalid data URL")
        s = s[comma + 1 :]
    raw = base64.b64decode(s)
    return Image.open(BytesIO(raw))


def _apply_gamma_lut(im_l, gamma: float):
    g = float(gamma)
    if g <= 0:
        return im_l
    if abs(g - 1.0) < 1e-6:
        return im_l
    inv = 1.0 / g
    lut = [max(0, min(255, int(round(((i / 255.0) ** inv) * 255.0)))) for i in range(256)]
    return im_l.point(lut)


def _quantize_levels(im_l, levels: int):
    lv = int(levels)
    if lv <= 1:
        return im_l
    if lv > 256:
        lv = 256
    step = 255.0 / (lv - 1)
    lut = [int(round(round(i / step) * step)) for i in range(256)]
    return im_l.point(lut)


def generate_raster_gcode(
    image_base64: str,
    speed: int = 1796,
    power: float = 100.0,
    passes: int = 1,
    origin: str = "bottom-left",
    width_mm: Optional[float] = None,
    height_mm: Optional[float] = None,
    mm_per_pixel: float = 0.1,
    invert_image: bool = False,
    shading: str = "grayscale",
    gamma: float = 1.0,
    levels: int = 0,
    thumbnail_mode: str = "match-input",
    thumbnail_contrast: float = 1.0,
    safe_mode: bool = False,
    accel_space_mm: float = 7.0,
    pixel_threshold: int = 5,
) -> str:
    """
    Prototype raster generator (OKU Desk dialect).

    - Uses `G1X...P<hex>` chunks (max 80 pixels per line)
    - Adds `$M` metadata + `$MT` thumbnail so the machine shows a preview
    - Scans bottom->top (like NomadTech), left->right only (prototype)

    Notes:
    - By default `invert_image=False` will invert the image (NomadTech behavior),
      so black-on-white burns the black parts.
    """
    from PIL import ImageOps  # type: ignore

    speed = max(10, min(8000, int(speed)))
    power = max(1.0, min(100.0, float(power)))
    passes = max(1, min(500, int(passes)))

    origin = (origin or "bottom-left").strip().lower()
    if origin not in ALLOWED_ORIGINS:
        origin = "bottom-left"

    im = _decode_image_data(image_base64)
    im = im.convert("RGBA")
    # Composite over white background to avoid transparency surprises
    bg = im.copy()
    bg.paste((255, 255, 255, 255), (0, 0, im.size[0], im.size[1]))
    bg.paste(im, mask=im.split()[3])
    im_l_input = bg.convert("L")

    # Match NomadTech: image is inverted by default
    im_l_burn = im_l_input if invert_image else ImageOps.invert(im_l_input)

    shading = (shading or "grayscale").strip().lower()
    if shading not in ("grayscale", "dither"):
        shading = "grayscale"

    # Gamma + optional levels (useful if firmware clamps values)
    im_l_burn = _apply_gamma_lut(im_l_burn, float(gamma))
    im_l_burn = _quantize_levels(im_l_burn, int(levels))

    if shading == "dither":
        # 1-bit dithering, then back to 0/255 so encoding stays identical.
        im_1 = im_l_burn.convert("1")  # default: Floyd–Steinberg
        im_l_burn = im_1.convert("L")

    w_px, h_px = im_l_burn.size
    if w_px <= 0 or h_px <= 0:
        raise ValueError("Invalid image size")

    # Determine physical size
    if width_mm is not None and width_mm > 0:
        mpp_x = float(width_mm) / w_px
    else:
        mpp_x = float(mm_per_pixel)

    if height_mm is not None and height_mm > 0:
        mpp_y = float(height_mm) / h_px
    else:
        mpp_y = float(mm_per_pixel)

    # For Oku raster, we use a single step (keep it simple)
    mmpixel = float((mpp_x + mpp_y) / 2.0)
    img_w_mm = w_px * mmpixel
    img_h_mm = h_px * mmpixel

    # Placement on bed (anchor based on origin)
    x0 = 0.0
    y0 = 0.0
    if origin in ("bottom-right", "top-right"):
        x0 = BED_W_MM - img_w_mm
    elif origin == "center":
        x0 = (BED_W_MM - img_w_mm) / 2.0

    if origin in ("top-left", "top-right"):
        y0 = BED_H_MM - img_h_mm
    elif origin == "center":
        y0 = (BED_H_MM - img_h_mm) / 2.0

    if x0 < 0 or y0 < 0 or (x0 + img_w_mm) > BED_W_MM + 1e-6 or (y0 + img_h_mm) > BED_H_MM + 1e-6:
        raise ValueError("Raster image does not fit in bed (adjust size or origin)")

    # Thumbnail
    thumbnail_mode = (thumbnail_mode or "match-input").strip().lower()
    if thumbnail_mode not in ("match-input", "match-burn"):
        thumbnail_mode = "match-input"
    thumb_source = im_l_input if thumbnail_mode == "match-input" else im_l_burn
    thumb_w, thumb_h, thumb_rows = _make_thumbnail_rows_from_image(thumb_source, contrast=float(thumbnail_contrast))

    # Estimate time very roughly: assume we traverse only drawn spans; prototype uses conservative estimate
    est_min = 1

    # Header
    out: List[str] = []
    out.extend(_make_meta_header_raster(
        bounds=(x0, x0 + img_w_mm, y0, y0 + img_h_mm),
        estimated_minutes=est_min,
        speed=speed,
        power_pct=power,
        passes=passes,
        thumb_w=thumb_w,
        thumb_h=thumb_h,
        thumb_rows_hex=thumb_rows,
    ))
    chunk_px = 40 if safe_mode else MAX_RASTER_PIXELS_PER_LINE
    accel_x = 2500.0 if safe_mode else 3500.0
    out.append(f"; Raster prototype v{RASTER_PROTO_VERSION} safe_mode={1 if safe_mode else 0} chunk_px={chunk_px} accel_x={accel_x:.0f}\n\n")
    out.append("G21 ; Units in mm\n\n")
    out.append("M5 ; Turn laser off\n\n")
    out.append(f"F{speed}\n\n")

    # Move to origin and set accel (NomadTech: M204 X3500.000)
    out.append(f"G0 X{_fmt3(x0)} Y{_fmt3(y0)}\n")
    out.append(f"M204 X{accel_x:.3f}\n")

    cur_x = float(x0)
    cur_y = float(y0)
    cur_x_s = _fmt3(cur_x)
    cur_y_s = _fmt3(cur_y)

    def emit_g0(x: Optional[float] = None, y: Optional[float] = None) -> None:
        nonlocal cur_x, cur_y, cur_x_s, cur_y_s
        nx = cur_x if x is None else float(x)
        ny = cur_y if y is None else float(y)
        nx_s = cur_x_s if x is None else _fmt3(nx)
        ny_s = cur_y_s if y is None else _fmt3(ny)
        if (abs(nx - cur_x) < RASTER_ZERO_MOVE_THRESHOLD_MM and abs(ny - cur_y) < RASTER_ZERO_MOVE_THRESHOLD_MM) or (
            nx_s == cur_x_s and ny_s == cur_y_s
        ):
            return
        if x is not None and y is not None:
            out.append(f"G0 X{nx_s} Y{ny_s}\n")
        elif x is not None:
            out.append(f"G0 X{nx_s}\n")
        elif y is not None:
            out.append(f"G0 Y{ny_s}\n")
        cur_x, cur_y = nx, ny
        cur_x_s, cur_y_s = nx_s, ny_s

    def emit_g1_raster(end_x: float, raster_hex: str) -> None:
        nonlocal cur_x, cur_x_s
        ex = float(end_x)
        ex_s = _fmt3(ex)
        if abs(ex - cur_x) < RASTER_ZERO_MOVE_THRESHOLD_MM or ex_s == cur_x_s:
            return
        out.append(f"G1X{ex_s}P{raster_hex}\n")
        cur_x = ex
        cur_x_s = ex_s

    # Pixels matrix bottom-to-top
    pixels = list(im_l_burn.getdata())
    rows = [pixels[i * w_px : (i + 1) * w_px] for i in range(h_px)]
    rows_bottom_to_top = rows[::-1]

    def first_nonblank(row):
        for i, v in enumerate(row):
            if v > pixel_threshold:
                return i
        return None

    def last_nonblank(row):
        for i in range(len(row) - 1, -1, -1):
            if row[i] > pixel_threshold:
                return i
        return None

    # For now: single-direction left-to-right
    for pass_idx in range(passes):
        if passes > 1:
            out.append(f"; Pass {pass_idx + 1}/{passes}\n")

        for y_idx, row in enumerate(rows_bottom_to_top):
            y = y0 + y_idx * mmpixel
            s = first_nonblank(row)
            e = last_nonblank(row)
            if s is None or e is None or e < s:
                continue  # blank row

            # Trim row and chunk
            trim = row[s : e + 1]
            start_x = x0 + s * mmpixel

            # accel move (simple): go to (start_x - accel, y) then to start_x
            ax = max(0.0, start_x - accel_space_mm)
            emit_g0(ax, y)
            emit_g0(start_x, None)

            drawn = 0
            while drawn < len(trim):
                chunk = trim[drawn : drawn + chunk_px]
                drawn += len(chunk)
                end_x = start_x + drawn * mmpixel
                # raster data = %02X of int((pixel * power)/100)
                raster_hex = "".join(f"{min(255, max(0, int((px * power) / 100))):02X}" for px in chunk)
                emit_g1_raster(end_x, raster_hex)

    out.append("\nM5 ; Turn laser off\n")
    emit_g0(0.0, 0.0)
    return "".join(out)

def _generate_gcode_from_paths(
    path_ds: Iterable[str],
    svg_h_mm: float,
    scale_x: float,
    scale_y: float,
    speed: int,
    power_pct: float,
    passes: int,
    origin: str,
    origin_x: float = None,
    origin_y: float = None,
) -> str:
    # 1) Parse paths to points (scaled to mm). NOTE: `path_ds` can be a list of raw `d` strings,
    # but for correct Inkscape output we prefer extracting drawables with transforms.
    all_paths: List[List[Pt]] = []
    if isinstance(path_ds, list) and path_ds and isinstance(path_ds[0], tuple):
        # (d, Mat) tuples
        for d, mat in path_ds:  # type: ignore[misc]
            pts = _path_to_points(d, scale_x, scale_y)
            if not pts:
                continue
            pts = _apply_mat_to_points(pts, mat)
            scaled = [Pt(p.x * scale_x, p.y * scale_y, p.cmd) for p in pts]
            scaled = _simplify_pts(scaled, SIMPLIFY_TOLERANCE_MM)
            all_paths.append(scaled)
    else:
        for d in path_ds:
            pts = _path_to_points(d, scale_x, scale_y)
            if not pts:
                continue
            scaled = [Pt(p.x * scale_x, p.y * scale_y, p.cmd) for p in pts]
            scaled = _simplify_pts(scaled, SIMPLIFY_TOLERANCE_MM)
            all_paths.append(scaled)

    if not all_paths:
        return "; No paths found\nM5\nG21\n"

    # 2) Compute bounds in machine space (Y flipped), estimate time
    minx = math.inf
    maxx = -math.inf
    miny = math.inf
    maxy = -math.inf
    est_min = 0.0

    for pts in all_paths:
        last_xy = None
        for p in pts:
            mx = p.x
            my = svg_h_mm - p.y  # Y flip
            minx = min(minx, mx)
            maxx = max(maxx, mx)
            miny = min(miny, my)
            maxy = max(maxy, my)

            if last_xy is not None:
                if p.cmd == "L":
                    est_min += _dist(last_xy, (mx, my)) / speed
                elif p.cmd == "M":
                    est_min += _dist(last_xy, (mx, my)) / RAPID_SPEED
            last_xy = (mx, my)

    # Multiply by passes (like JS: per job)
    est_min *= max(1, int(passes))

    # 3) Safety: auto-fit within bed if needed (prevents out-of-range crashes)
    # We scale uniformly (preserve aspect ratio) in machine space.
    width = (maxx - minx) if (math.isfinite(maxx) and math.isfinite(minx)) else 0.0
    height = (maxy - miny) if (math.isfinite(maxy) and math.isfinite(miny)) else 0.0

    fit_scale = 1.0
    if width > 0 and height > 0:
        if width > BED_W_MM or height > BED_H_MM:
            fit_scale = min(BED_W_MM / width, BED_H_MM / height) * 0.99  # tiny margin
            if fit_scale <= 0 or not math.isfinite(fit_scale):
                raise ValueError("SVG bounds invalid: cannot scale to fit bed")

    if abs(fit_scale - 1.0) > 1e-9:
        # Scale all paths and svg height (keeps Y flip correct)
        svg_h_mm *= fit_scale
        all_paths = [[Pt(p.x * fit_scale, p.y * fit_scale, p.cmd) for p in pts] for pts in all_paths]
        # Recompute bounds quickly in machine space
        minx = math.inf
        maxx = -math.inf
        miny = math.inf
        maxy = -math.inf
        for pts in all_paths:
            for p in pts:
                mx = p.x
                my = svg_h_mm - p.y
                minx = min(minx, mx)
                maxx = max(maxx, mx)
                miny = min(miny, my)
                maxy = max(maxy, my)

    # 4) Apply job origin (user's 0,0 reference on the bed)
    origin = (origin or "bottom-left").strip().lower()
    if origin not in ALLOWED_ORIGINS:
        origin = "bottom-left"

    width = (maxx - minx) if (math.isfinite(maxx) and math.isfinite(minx)) else 0.0
    height = (maxy - miny) if (math.isfinite(maxy) and math.isfinite(miny)) else 0.0
    width = max(0.0, width)
    height = max(0.0, height)

    # Base shift so min corner starts at (0,0)
    offset_x = -minx if math.isfinite(minx) else 0.0
    offset_y = -miny if math.isfinite(miny) else 0.0

    # Then anchor within the bed based on origin choice
    if origin == "custom":
        if origin_x is not None and origin_y is not None:
            # Custom origin: user specifies exact X, Y position (in machine coordinates, bottom-left origin)
            # We need to place the design so its top-left corner (after offset) is at (origin_x, origin_y)
            # But SVG Y is top-down, machine Y is bottom-up, so we flip
            offset_x += origin_x
            offset_y += (BED_H_MM - origin_y - height)  # Flip Y: machine Y=0 is bottom, SVG Y=0 is top
        else:
            # Fallback to bottom-left if custom coords not provided
            origin = "bottom-left"
    
    if origin != "custom":
        if origin in ("bottom-right", "top-right"):
            offset_x += (BED_W_MM - width)
        elif origin == "center":
            offset_x += (BED_W_MM - width) / 2.0

        if origin in ("top-left", "top-right"):
            offset_y += (BED_H_MM - height)
        elif origin == "center":
            offset_y += (BED_H_MM - height) / 2.0

    # Apply offsets to bounds
    b_minx = (minx + offset_x) if math.isfinite(minx) else 0.0
    b_maxx = (maxx + offset_x) if math.isfinite(maxx) else 0.0
    b_miny = (miny + offset_y) if math.isfinite(miny) else 0.0
    b_maxy = (maxy + offset_y) if math.isfinite(maxy) else 0.0

    # Final hard safety check: must fit within bed
    if b_minx < -1e-6 or b_miny < -1e-6 or b_maxx > BED_W_MM + 1e-6 or b_maxy > BED_H_MM + 1e-6:
        raise ValueError(
            f"Generated coordinates out of bed bounds after fit/offset: "
            f"X[{b_minx:.3f},{b_maxx:.3f}] Y[{b_miny:.3f},{b_maxy:.3f}] "
            f"(bed {BED_W_MM:.0f}x{BED_H_MM:.0f} mm)"
        )

    # 4b) Task 1: optimize path order to minimize rapid travel. This is a single
    # job/legacy call, so all_paths is one batch -- safe to reorder as a whole.
    # `local_start` is (0,0) in *machine* space (the physical head-start
    # position), expressed back in this function's pre-offset/pre-flip point
    # space; since translation and the Y-flip are both distance-preserving,
    # nearest-neighbour distances computed here equal machine-space distances.
    local_start = (-offset_x, svg_h_mm + offset_y)
    all_paths = _optimize_path_order(all_paths, start_point=local_start)

    # 5) Power scaling (Python original: ceil(power * 2.55))
    power_s = int(math.ceil(float(power_pct) * 2.55))
    power_s = max(0, min(S_MAX, power_s))

    # 6) Thumbnail (required for preview; matches NomadTech vector script behavior)
    segments = _segments_from_paths(all_paths, svg_h_mm, offset_x, offset_y)
    thumb_w, thumb_h, thumb_rows = _make_thumbnail_rows(segments, (b_minx, b_maxx, b_miny, b_maxy))

    # 7) Build G-code as strings WITH newlines (like original scripts)
    out: List[str] = []
    out.extend(_make_meta_header((b_minx, b_maxx, b_miny, b_maxy), est_min, speed, power_pct, passes, thumb_w, thumb_h, thumb_rows))
    out.append("M5 ; Turn laser off\n")
    out.append("G21 ; Units in mm\n")
    out.append("\n")

    # For now: single job settings, repeat passes
    for pidx in range(max(1, int(passes))):
        if passes and passes > 1:
            out.append(f"; --- Pass {pidx + 1}/{passes} ---\n")
        out.append(f"F{int(speed)}\n")

        # Task 2: alternate path-list order each pass (boustrophedon at the
        # path level) so the head doesn't rapid all the way back to the first
        # path after finishing at the last one on the previous pass.
        seq = all_paths if pidx % 2 == 0 else list(reversed(all_paths))
        for pts in seq:
            last = None  # last machine coord (with offsets)
            laser_on = False
            first_move = None

            for i, pt in enumerate(pts):
                mx = (pt.x) + offset_x
                my = (svg_h_mm - pt.y) + offset_y  # flip + offset

                if last is not None and abs(mx - last[0]) < ZERO_MOVE_THRESHOLD and abs(my - last[1]) < ZERO_MOVE_THRESHOLD:
                    # Skip redundant close (last point == first move)
                    if i == len(pts) - 1 and first_move is not None and abs(mx - first_move[0]) < ZERO_MOVE_THRESHOLD and abs(my - first_move[1]) < ZERO_MOVE_THRESHOLD:
                        continue
                    if pt.cmd != "M":
                        continue

                if pt.cmd == "M":
                    if laser_on:
                        out.append("M5\n")
                        laser_on = False
                    out.append(f"G0 X{_fmt(mx)} Y{_fmt(my)}\n")
                    if first_move is None:
                        first_move = (mx, my)
                elif pt.cmd == "L":
                    if not laser_on:
                        out.append(f"M3 S{power_s}\n")
                        laser_on = True
                    if i == len(pts) - 1 and first_move is not None and abs(mx - first_move[0]) < ZERO_MOVE_THRESHOLD and abs(my - first_move[1]) < ZERO_MOVE_THRESHOLD:
                        continue
                    out.append(f"G1 X{_fmt(mx)} Y{_fmt(my)}\n")

                last = (mx, my)

            if laser_on:
                out.append("M5\n")

    out.append("G0 X0 Y0\n")
    out.append("\n")
    out.append("M5 ; Turn laser off\n")
    return "".join(out)


def generate_vector_gcode(svg_path, speed=1000, power=100.0, passes=1, origin: str = "bottom-left"):
    """
    Génère du G-code vectoriel depuis un fichier SVG
    
    Args:
        svg_path: Chemin vers le fichier SVG
        speed: Vitesse en mm/min (10-6000)
        power: Puissance laser en % (1-100)
        passes: Nombre de passes (1-500)
    
    Returns:
        str: Contenu du fichier G-code
    """
    svg_path = str(svg_path)
    p = Path(svg_path)
    if not p.exists():
        raise FileNotFoundError(f"SVG file not found: {svg_path}")

    # Clamp inputs (same as API layer, but keep it safe if called directly)
    speed_i = max(10, min(6000, int(speed)))
    power_f = max(1.0, min(100.0, float(power)))
    passes_i = max(1, min(500, int(passes)))

    svg_bytes = p.read_bytes()
    svg_root = etree.fromstring(svg_bytes)

    svg_w_mm, svg_h_mm, scale_x, scale_y = _get_svg_dimensions_and_scale(svg_root)
    # Extract drawables (paths + basic shapes) with transforms, convert to path "d"
    drawables = _extract_drawables(svg_root)
    path_ds: List[Tuple[str, Mat]] = []
    for el, mat in drawables:
        lname = _local_name(el)
        d: Optional[str] = None
        if lname == "path":
            d = el.get("d")
        elif lname == "rect":
            d = _rect_to_path_d(el)
        elif lname in ("circle", "ellipse"):
            d = _circle_ellipse_to_path_d(el)
        elif lname == "line":
            d = _line_to_path_d(el)
        elif lname in ("polyline", "polygon"):
            d = _poly_to_path_d(el)

        if d and str(d).strip():
            path_ds.append((str(d), mat))

    return _generate_gcode_from_paths(
        path_ds=path_ds,
        svg_h_mm=svg_h_mm,
        scale_x=scale_x,
        scale_y=scale_y,
        speed=speed_i,
        power_pct=power_f,
        passes=passes_i,
        origin=origin,
        origin_x=None,  # Single-job mode doesn't support custom origin yet
        origin_y=None,
    )


def _parse_style(style: Optional[str]) -> dict:
    if not style:
        return {}
    out = {}
    for part in str(style).split(';'):
        if ':' not in part:
            continue
        k, v = part.split(':', 1)
        out[k.strip().lower()] = v.strip()
    return out


def _normalize_color(c: Optional[str]) -> Optional[str]:
    if not c:
        return None
    c = str(c).strip().lower()
    if not c or c == 'none':
        return None
    if c.startswith('#'):
        if len(c) == 4:
            return '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3]
        return c
    if c.startswith('rgb'):
        nums = re.findall(r'\d+', c)
        if len(nums) >= 3:
            r = int(nums[0]); g = int(nums[1]); b = int(nums[2])
            return f"#{r:02x}{g:02x}{b:02x}"
    named = {
        'red': '#ff0000',
        'green': '#00ff00',
        'blue': '#0000ff',
        'black': '#000000',
        'white': '#ffffff',
        'yellow': '#ffff00',
        'cyan': '#00ffff',
        'magenta': '#ff00ff',
    }
    return named.get(c, c)


def _element_color(el) -> Optional[str]:
    # Match frontend behavior: stroke, else style stroke, else fill
    stroke = el.get('stroke')
    if not stroke or stroke == 'none':
        style = _parse_style(el.get('style'))
        stroke = style.get('stroke')
    if not stroke or stroke == 'none':
        fill = el.get('fill')
        if fill and fill != 'none':
            stroke = fill
    return _normalize_color(stroke)


def generate_vector_gcode_advanced(svg_path: str, jobs: list, origin: str = "bottom-left", origin_x: float = None, origin_y: float = None) -> str:
    """
    Advanced generation: use ordered per-color jobs coming from the UI.
    `jobs` items expected like: {color, enabled, speed, power, passes}
    """
    svg_path = str(svg_path)
    p = Path(svg_path)
    if not p.exists():
        raise FileNotFoundError(f"SVG file not found: {svg_path}")

    svg_bytes = p.read_bytes()
    svg_root = etree.fromstring(svg_bytes)

    svg_w_mm, svg_h_mm, scale_x, scale_y = _get_svg_dimensions_and_scale(svg_root)

    # Build requested order + settings by color
    requested = []
    settings = {}
    for j in jobs or []:
        try:
            color = _normalize_color(j.get('color'))
            if not color:
                continue
            enabled = bool(j.get('enabled', True))
            if not enabled:
                continue
            speed = max(10, min(6000, int(j.get('speed', 1000))))
            power = max(1.0, min(100.0, float(j.get('power', 100.0))))
            passes = max(1, min(500, int(j.get('passes', 1))))
            requested.append(color)
            settings[color] = {'speed': speed, 'power': power, 'passes': passes}
        except Exception:
            continue

    if not requested:
        # fallback: single global
        return generate_vector_gcode(svg_path=svg_path, speed=1000, power=100.0, passes=1, origin=origin)

    # Extract drawables + group by normalized color
    drawables = _extract_drawables(svg_root)
    by_color = {c: [] for c in requested}
    for el, mat in drawables:
        c = _element_color(el)
        if not c or c not in by_color:
            continue

        lname = _local_name(el)
        d = None
        if lname == "path":
            d = el.get("d")
        elif lname == "rect":
            d = _rect_to_path_d(el)
        elif lname in ("circle", "ellipse"):
            d = _circle_ellipse_to_path_d(el)
        elif lname == "line":
            d = _line_to_path_d(el)
        elif lname in ("polyline", "polygon"):
            d = _poly_to_path_d(el)
        if d and str(d).strip():
            by_color[c].append((str(d), mat))

    # Build job batches in requested order
    batches = []
    for c in requested:
        paths = by_color.get(c) or []
        if not paths:
            continue
        s = settings[c]
        batches.append({'color': c, 'paths': paths, **s})

    if not batches:
        return generate_vector_gcode(svg_path=svg_path, speed=1000, power=100.0, passes=1, origin=origin)

    return _generate_gcode_from_job_batches(
        batches=batches,
        svg_h_mm=svg_h_mm,
        scale_x=scale_x,
        scale_y=scale_y,
        origin=origin,
        origin_x=origin_x,
        origin_y=origin_y,
    )


def _generate_gcode_from_job_batches(
    batches: list,
    svg_h_mm: float,
    scale_x: float,
    scale_y: float,
    origin: str,
    origin_x: float = None,
    origin_y: float = None,
) -> str:
    """
    Multi-job generator: emits a single file with one metadata block + thumbnail,
    then executes jobs in order (each with its own speed/power/passes).
    """
    # Parse/scale all paths per batch
    jobs_pts = []
    for b in batches:
        paths_pts = []
        for d, mat in b['paths']:
            pts = _path_to_points(d, scale_x, scale_y)
            if not pts:
                continue
            pts = _apply_mat_to_points(pts, mat)
            scaled = [Pt(p.x * scale_x, p.y * scale_y, p.cmd) for p in pts]
            scaled = _simplify_pts(scaled, SIMPLIFY_TOLERANCE_MM)
            paths_pts.append(scaled)
        if paths_pts:
            jobs_pts.append({**b, 'paths_pts': paths_pts})

    if not jobs_pts:
        return "; No paths found\nM5\nG21\n"

    # Compute global bounds/time in machine space
    minx = math.inf; maxx = -math.inf; miny = math.inf; maxy = -math.inf
    est_min = 0.0
    for job in jobs_pts:
        speed = int(job['speed'])
        job_est_min = 0.0
        for pts in job['paths_pts']:
            last_xy = None
            for p in pts:
                mx = p.x
                my = svg_h_mm - p.y
                minx = min(minx, mx); maxx = max(maxx, mx)
                miny = min(miny, my); maxy = max(maxy, my)
                if last_xy is not None:
                    if p.cmd == 'L':
                        job_est_min += _dist(last_xy, (mx, my)) / speed
                    elif p.cmd == 'M':
                        job_est_min += _dist(last_xy, (mx, my)) / RAPID_SPEED
                last_xy = (mx, my)
        est_min += job_est_min * max(1, int(job.get('passes', 1)))

    # Fit scale to bed (uniform)
    width = (maxx - minx) if (math.isfinite(maxx) and math.isfinite(minx)) else 0.0
    height = (maxy - miny) if (math.isfinite(maxy) and math.isfinite(miny)) else 0.0
    fit_scale = 1.0
    if width > 0 and height > 0 and (width > BED_W_MM or height > BED_H_MM):
        fit_scale = min(BED_W_MM / width, BED_H_MM / height) * 0.99
    if abs(fit_scale - 1.0) > 1e-9:
        svg_h_mm *= fit_scale
        # scale all points
        for job in jobs_pts:
            scaled_paths = []
            for pts in job['paths_pts']:
                scaled_paths.append([Pt(p.x * fit_scale, p.y * fit_scale, p.cmd) for p in pts])
            job['paths_pts'] = scaled_paths
        # recompute bounds quickly
        minx = math.inf; maxx = -math.inf; miny = math.inf; maxy = -math.inf
        for job in jobs_pts:
            for pts in job['paths_pts']:
                for p in pts:
                    mx = p.x
                    my = svg_h_mm - p.y
                    minx = min(minx, mx); maxx = max(maxx, mx)
                    miny = min(miny, my); maxy = max(maxy, my)

    # Compute offsets based on origin
    origin = (origin or "bottom-left").strip().lower()
    if origin not in ALLOWED_ORIGINS:
        origin = "bottom-left"
    w = max(0.0, maxx - minx)
    h = max(0.0, maxy - miny)
    offset_x = -minx if math.isfinite(minx) else 0.0
    offset_y = -miny if math.isfinite(miny) else 0.0
    
    if origin == "custom":
        if origin_x is not None and origin_y is not None:
            # Custom origin: user specifies exact X, Y position (in machine coordinates, bottom-left origin)
            # We need to place the design so its top-left corner (after offset) is at (origin_x, origin_y)
            # But SVG Y is top-down, machine Y is bottom-up, so we flip
            offset_x += origin_x
            offset_y += (BED_H_MM - origin_y - h)  # Flip Y: machine Y=0 is bottom, SVG Y=0 is top
        else:
            # Fallback to bottom-left if custom coords not provided
            origin = "bottom-left"
    
    if origin != "custom":
        if origin in ("bottom-right", "top-right"):
            offset_x += (BED_W_MM - w)
        elif origin == "center":
            offset_x += (BED_W_MM - w) / 2.0
        if origin in ("top-left", "top-right"):
            offset_y += (BED_H_MM - h)
        elif origin == "center":
            offset_y += (BED_H_MM - h) / 2.0

    b_minx = (minx + offset_x) if math.isfinite(minx) else 0.0
    b_maxx = (maxx + offset_x) if math.isfinite(maxx) else 0.0
    b_miny = (miny + offset_y) if math.isfinite(miny) else 0.0
    b_maxy = (maxy + offset_y) if math.isfinite(maxy) else 0.0

    if b_minx < -1e-6 or b_miny < -1e-6 or b_maxx > BED_W_MM + 1e-6 or b_maxy > BED_H_MM + 1e-6:
        raise ValueError(
            f"Generated coordinates out of bed bounds after fit/offset: "
            f"X[{b_minx:.3f},{b_maxx:.3f}] Y[{b_miny:.3f},{b_maxy:.3f}]"
        )

    # Task 1: optimize path order within each job/color batch. Never reorder
    # across batches -- job order is user-controlled (cut-before-engrave etc.)
    # and each job here gets its own independent nearest-neighbour tour,
    # chained head-to-head so job N+1's tour starts from wherever job N's
    # (pass-alternation-aware) tour actually ends.
    local_start = (-offset_x, svg_h_mm + offset_y)
    running_head = local_start
    for job in jobs_pts:
        ordered = _optimize_path_order(job['paths_pts'], start_point=running_head)
        job['paths_pts'] = ordered
        passes_n = int(job.get('passes', 1))
        _, exit0 = _path_endpoints(ordered[0])
        _, exitN = _path_endpoints(ordered[-1])
        # Task 2 reverses path-list order on odd passes; the actual head
        # position after this job's passes therefore depends on whether the
        # last pass ran forward (ends at last path's exit) or reversed
        # (ends at first path's own exit, since only list order flips).
        running_head = exitN if passes_n % 2 == 1 else exit0

    # Thumbnail uses all segments
    all_paths_flat = []
    for job in jobs_pts:
        all_paths_flat.extend(job['paths_pts'])
    segments = _segments_from_paths(all_paths_flat, svg_h_mm, offset_x, offset_y)
    thumb_w, thumb_h, thumb_rows = _make_thumbnail_rows(segments, (b_minx, b_maxx, b_miny, b_maxy))

    # Meta header uses first job settings (single-op header)
    first = jobs_pts[0]
    out: List[str] = []
    out.extend(_make_meta_header(
        (b_minx, b_maxx, b_miny, b_maxy),
        est_min,
        int(first['speed']),
        float(first['power']),
        int(first.get('passes', 1)),
        thumb_w,
        thumb_h,
        thumb_rows
    ))
    out.append("M5 ; Turn laser off\n")
    out.append("G21 ; Units in mm\n")
    out.append("\n")

    # Emit jobs in order
    for job in jobs_pts:
        color = job.get('color', '')
        speed = int(job['speed'])
        power_pct = float(job['power'])
        passes = int(job.get('passes', 1))
        power_s = int(math.ceil(power_pct * 2.55))
        power_s = max(0, min(S_MAX, power_s))

        out.append(f"; --- Job {color} ---\n")
        for pidx in range(max(1, passes)):
            if passes > 1:
                out.append(f"; Pass {pidx + 1}/{passes}\n")
            out.append(f"F{speed}\n")

            # Task 2: alternate path-list order each pass within this job.
            seq = job['paths_pts'] if pidx % 2 == 0 else list(reversed(job['paths_pts']))
            for pts in seq:
                last = None
                laser_on = False
                first_move = None
                for i, pt in enumerate(pts):
                    mx = pt.x + offset_x
                    my = (svg_h_mm - pt.y) + offset_y
                    if last is not None and abs(mx - last[0]) < ZERO_MOVE_THRESHOLD and abs(my - last[1]) < ZERO_MOVE_THRESHOLD:
                        if i == len(pts) - 1 and first_move is not None and abs(mx - first_move[0]) < ZERO_MOVE_THRESHOLD and abs(my - first_move[1]) < ZERO_MOVE_THRESHOLD:
                            continue
                        if pt.cmd != "M":
                            continue
                    if pt.cmd == "M":
                        if laser_on:
                            out.append("M5\n")
                            laser_on = False
                        out.append(f"G0 X{_fmt(mx)} Y{_fmt(my)}\n")
                        if first_move is None:
                            first_move = (mx, my)
                    elif pt.cmd == "L":
                        if not laser_on:
                            out.append(f"M3 S{power_s}\n")
                            laser_on = True
                        if i == len(pts) - 1 and first_move is not None and abs(mx - first_move[0]) < ZERO_MOVE_THRESHOLD and abs(my - first_move[1]) < ZERO_MOVE_THRESHOLD:
                            continue
                        out.append(f"G1 X{_fmt(mx)} Y{_fmt(my)}\n")
                    last = (mx, my)
                if laser_on:
                    out.append("M5\n")

    out.append("G0 X0 Y0\n")
    out.append("\n")
    out.append("M5 ; Turn laser off\n")
    return "".join(out)


#
# NOTE: Raster generation is implemented above as `generate_raster_gcode(image_base64, ...)`.
#
