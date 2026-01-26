import base64
import math
from io import BytesIO
from typing import List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageOps

BED_W_MM = 500.0
BED_H_MM = 285.0

THUMB_MAX_W = 225
THUMB_MAX_H = 159

MAX_RASTER_PIXELS_PER_LINE = 80
ZERO_MOVE_THRESHOLD_MM = 0.005

PROTO_VERSION = "0.2.0"

ALLOWED_ORIGINS = (
    "bottom-left",
    "bottom-right",
    "top-left",
    "top-right",
    "center",
)


def _fmt3(n: float) -> str:
    return f"{float(n):.3f}"


def _decode_image_data(image_base64: str) -> Image.Image:
    """
    Accepts base64 string or data URL: data:image/png;base64,...
    """
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


def _make_thumbnail_rows_from_image(im_l: Image.Image, *, contrast: float = 1.0) -> Tuple[int, int, List[str]]:
    img = im_l.copy()
    img.thumbnail((THUMB_MAX_W, THUMB_MAX_H))
    img = img.convert("L")
    if contrast and float(contrast) != 1.0:
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
    minx, maxx, miny, maxy = bounds
    w = max(0.0, maxx - minx)
    h = max(0.0, maxy - miny)

    meta: List[str] = []
    meta.append(";$M Meta untilchar 000000\n")
    meta.append(f";$M Frame X{w:.2f} Y{h:.2f}\n")
    meta.append(f";$M Pos X{minx:.2f} Y{miny:.2f}\n")
    meta.append(f";$M Margin {float(margin):.2f}\n")
    meta.append(";$M NumOps 1\n")
    meta.append(";$M Op 0\n")
    meta.append(";$M Type Raster\n")
    meta.append(f";$M Speed {int(speed)}\n")
    meta.append(f";$M Power {float(power_pct):.1f}\n")
    meta.append(f";$M Rep {int(passes)}\n")
    meta.append(f";$M Time {int(math.ceil(max(0.0, estimated_minutes)))}\n")
    meta.append(f";$M Thumb start X{int(thumb_w)} Y{int(thumb_h)}\n")
    for row in thumb_rows_hex:
        meta.append(f";$MT {row}\n")
    meta.append(";$M Thumb end\n\n")

    meta_len = sum(len(s) for s in meta)
    meta[0] = f";$M Meta untilchar {meta_len:06d}\n"
    return meta


def _apply_gamma_lut(im_l: Image.Image, gamma: float) -> Image.Image:
    g = float(gamma)
    if g <= 0:
        return im_l
    if abs(g - 1.0) < 1e-6:
        return im_l
    inv = 1.0 / g
    lut = [max(0, min(255, int(round(((i / 255.0) ** inv) * 255.0)))) for i in range(256)]
    return im_l.point(lut)


def _quantize_levels(im_l: Image.Image, levels: int) -> Image.Image:
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
    OKU raster prototype:
    - G1X...P<hex> chunks (max 80 pixels/line)
    - $M/$MT thumbnail preview
    - left-to-right scanning only (prototype)
    """
    speed = max(10, min(8000, int(speed)))
    power = max(1.0, min(100.0, float(power)))
    passes = max(1, min(500, int(passes)))

    origin = (origin or "bottom-left").strip().lower()
    if origin not in ALLOWED_ORIGINS:
        origin = "bottom-left"

    im = _decode_image_data(image_base64).convert("RGBA")
    # composite over white background
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.paste(im, mask=im.split()[3])
    im_l_input = bg.convert("L")

    # NomadTech behavior: inverted by default
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

    if width_mm is not None and width_mm > 0:
        mpp_x = float(width_mm) / w_px
    else:
        mpp_x = float(mm_per_pixel)

    if height_mm is not None and height_mm > 0:
        mpp_y = float(height_mm) / h_px
    else:
        mpp_y = float(mm_per_pixel)

    mmpixel = float((mpp_x + mpp_y) / 2.0)
    img_w_mm = w_px * mmpixel
    img_h_mm = h_px * mmpixel

    # place on bed based on origin
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

    thumbnail_mode = (thumbnail_mode or "match-input").strip().lower()
    if thumbnail_mode not in ("match-input", "match-burn"):
        thumbnail_mode = "match-input"
    thumb_source = im_l_input if thumbnail_mode == "match-input" else im_l_burn
    thumb_w, thumb_h, thumb_rows = _make_thumbnail_rows_from_image(thumb_source, contrast=float(thumbnail_contrast))
    est_min = 1

    out: List[str] = []
    out.extend(
        _make_meta_header_raster(
            bounds=(x0, x0 + img_w_mm, y0, y0 + img_h_mm),
            estimated_minutes=est_min,
            speed=speed,
            power_pct=power,
            passes=passes,
            thumb_w=thumb_w,
            thumb_h=thumb_h,
            thumb_rows_hex=thumb_rows,
        )
    )

    chunk_px = 40 if safe_mode else MAX_RASTER_PIXELS_PER_LINE
    accel_x = 2500.0 if safe_mode else 3500.0
    out.append(f"; Raster prototype v{PROTO_VERSION} safe_mode={1 if safe_mode else 0} chunk_px={chunk_px} accel_x={accel_x:.0f}\n\n")
    out.append("G21 ; Units in mm\n\n")
    out.append("M5 ; Turn laser off\n\n")
    out.append(f"F{speed}\n\n")
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
        # Important: compare both by numeric threshold AND by formatted coordinates.
        # Some crashes were triggered by consecutive commands that *format* to the same X/Y.
        nx_s = cur_x_s if x is None else _fmt3(nx)
        ny_s = cur_y_s if y is None else _fmt3(ny)
        if (abs(nx - cur_x) < ZERO_MOVE_THRESHOLD_MM and abs(ny - cur_y) < ZERO_MOVE_THRESHOLD_MM) or (
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
        if abs(ex - cur_x) < ZERO_MOVE_THRESHOLD_MM or ex_s == cur_x_s:
            return
        out.append(f"G1X{ex_s}P{raster_hex}\n")
        cur_x = ex
        cur_x_s = ex_s

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

    for pass_idx in range(passes):
        if passes > 1:
            out.append(f"; Pass {pass_idx + 1}/{passes}\n")
        for y_idx, row in enumerate(rows_bottom_to_top):
            y = y0 + y_idx * mmpixel
            s = first_nonblank(row)
            e = last_nonblank(row)
            if s is None or e is None or e < s:
                continue
            trim = row[s : e + 1]
            start_x = x0 + s * mmpixel

            ax = max(0.0, start_x - accel_space_mm)
            emit_g0(ax, y)
            emit_g0(start_x, None)

            drawn = 0
            while drawn < len(trim):
                chunk = trim[drawn : drawn + chunk_px]
                drawn += len(chunk)
                end_x = start_x + drawn * mmpixel
                raster_hex = "".join(f"{min(255, max(0, int((px * power) / 100))):02X}" for px in chunk)
                emit_g1_raster(end_x, raster_hex)

    out.append("\nM5 ; Turn laser off\n")
    emit_g0(0.0, 0.0)
    return "".join(out)

