"""
CS Scanner Pro V6.4 - Mobile UI & Android APK Ready Edition
- Tương thích hoàn toàn Flet 0.70+ (Android APK / serious_python) và Flet 0.21 -> 0.25+ (PC)
- Đã sửa lỗi AttributeError: module 'flet' has no attribute 'app' (tự chuyển sang ft.run)
- Đã đồng bộ FilePicker & Share Service cho cả Android (async services) và Windows (overlay)
- Giao diện Mobile chuẩn ngón cái: Bottom Action Bar, Contextual Bar, Studio 3 Tab gọn gàng
- Đầy đủ 10 tính năng:
  1. Nén PDF tự động theo dung lượng mục tiêu (dưới X MB)
  2. Thùng rác thông minh (lưu 7 ngày, khôi phục tài liệu & trang lẻ)
  3. Cảnh báo ảnh mờ / thiếu sáng ngay khi chụp hoặc tải lên
  4. Sao lưu & Khôi phục toàn bộ dữ liệu ra file .zip
  5. Đóng dấu chữ mờ (Watermark) hỗ trợ tiếng Việt (Pillow / OpenCV fallback)
  6. Màn hình che thông tin nhạy cảm (Vẽ ô đen / Làm mờ Pixel / Xóa trắng, chạm vào ô để xóa)
  7. Ghép 2, 4 hoặc 6 ảnh vào 1 trang A4 chuẩn
  8. Tách nền chữ ký tự động & Kéo thả vị trí trực quan
  9. Quản lý Thư mục (Folder), Tìm kiếm & Sắp xếp tài liệu
  10. Chụp trực tiếp từ Camera trong app (hoặc chuyển sang Camera hệ thống trên Android)
"""
import base64
import json
import os
import re
import shutil
import tempfile
import threading
import time
import unicodedata
import uuid
import warnings
import zipfile

import cv2
import flet as ft
import numpy as np

warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    from PIL import Image as PILImage, ImageDraw as PILDraw, ImageFont as PILFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# =====================================================================
# 0. LỚP TƯƠNG THÍCH FLET MỌI PHIÊN BẢN (0.2x -> 0.70+)
# =====================================================================
Colors = getattr(ft, "Colors", None) or getattr(ft, "colors", None)
Icons = getattr(ft, "Icons", None) or getattr(ft, "icons", None)
FIT = getattr(ft, "BoxFit", None) or getattr(ft, "ImageFit", None)
IMG_OLD = hasattr(ft.Image, "src_base64")
NEW_FLET = hasattr(ft, "Service") or not hasattr(ft, "app")
DDOpt = getattr(ft, "DropdownOption", None) or ft.dropdown.Option


def _tolerant(cls):
    """Bỏ qua các tham số không hỗ trợ giữa các phiên bản Flet."""
    def build(*args, **kw):
        for _ in range(10):
            try:
                return cls(*args, **kw)
            except TypeError as ex:
                m = re.search(r"unexpected keyword argument '(\w+)'", str(ex))
                if not m or m.group(1) not in kw:
                    raise
                kw.pop(m.group(1))
        return cls(*args, **kw)

    build.__name__ = getattr(cls, "__name__", "control")
    return build


for _n in ("TextField", "Switch", "Checkbox", "Slider", "Dropdown", "Container", "Text", "Row", "Column",
           "IconButton", "Image", "ProgressBar", "PopupMenuButton", "ListTile", "Card", "AlertDialog",
           "BottomSheet", "SnackBar", "GestureDetector", "InteractiveViewer", "Stack", "Icon", "Divider",
           "TextButton", "ElevatedButton", "OutlinedButton", "Button", "SafeArea"):
    _c = getattr(ft, _n, None)
    if isinstance(_c, type):
        setattr(ft, _n, _tolerant(_c))

Btn = getattr(ft, "ElevatedButton", None) or getattr(ft, "Button", None)
OutBtn = getattr(ft, "OutlinedButton", None) or getattr(ft, "Button", None)

PLACEHOLDER_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def pad_sym(h=0, v=0):
    P = getattr(ft, "Padding", None)
    if P is not None and hasattr(P, "symmetric"):
        return P.symmetric(horizontal=h, vertical=v)
    return ft.padding.symmetric(horizontal=h, vertical=v)


def mar_sym(h=0, v=0):
    M = getattr(ft, "Margin", None)
    if M is not None and hasattr(M, "symmetric"):
        return M.symmetric(horizontal=h, vertical=v)
    return ft.margin.symmetric(horizontal=h, vertical=v)


def border_all(width, color):
    B = getattr(ft, "Border", None)
    if B is not None and hasattr(B, "all"):
        return B.all(width, color)
    return ft.border.all(width, color)


_A = getattr(ft, "Alignment", None)
ALIGN_CENTER = _A.CENTER if (_A is not None and hasattr(_A, "CENTER")) else ft.alignment.center


def make_img(b64="", **kw):
    b64 = b64 or PLACEHOLDER_B64
    if IMG_OLD:
        return ft.Image(src_base64=b64, **kw)
    return ft.Image(src=b64, **kw)


def set_img(img, b64):
    b64 = b64 or PLACEHOLDER_B64
    if IMG_OLD:
        img.src_base64 = b64
    else:
        img.src = b64


def set_btn_text(btn, txt: str):
    if hasattr(btn, "text"):
        btn.text = txt
    elif hasattr(btn, "content"):
        btn.content = ft.Text(txt)


def pm_item(label, cb):
    try:
        return ft.PopupMenuItem(text=label, on_click=cb)
    except TypeError:
        return ft.PopupMenuItem(content=ft.Text(label), on_click=cb)


def drag_delta(e):
    dx = getattr(e, "delta_x", None)
    dy = getattr(e, "delta_y", None)
    if dx is None or dy is None:
        d = getattr(e, "local_delta", None) or getattr(e, "global_delta", None)
        if d is not None:
            dx, dy = getattr(d, "x", 0), getattr(d, "y", 0)
    return float(dx or 0.0), float(dy or 0.0)


def drag_pos(e):
    lx = getattr(e, "local_x", None)
    ly = getattr(e, "local_y", None)
    if lx is None or ly is None:
        lp = getattr(e, "local_position", None)
        if lp is not None:
            lx, ly = getattr(lp, "x", None), getattr(lp, "y", None)
    if lx is None or ly is None:
        return None, None
    return float(lx), float(ly)


# =====================================================================
# 1. LƯU TRỮ TRÊN ĐĨA & QUẢN LÝ FILE AN TOÀN UTF-8
# =====================================================================
def _init_dirs():
    cands = [
        os.environ.get("FLET_APP_STORAGE_DATA"),
        os.path.join(os.path.expanduser("~"), ".cs_scanner"),
        os.path.abspath("cs_scanner_data"),
    ]
    for base in cands:
        if not base:
            continue
        try:
            root = os.path.join(base, "cs_scanner")
            for sub in ("pages", "docs", "exports", "trash", "signatures"):
                os.makedirs(os.path.join(root, sub), exist_ok=True)
            return root
        except Exception:
            continue
    raise RuntimeError("Không tạo được thư mục lưu dữ liệu")


DATA_DIR = _init_dirs()
PAGES_DIR = os.path.join(DATA_DIR, "pages")
DOCS_DIR = os.path.join(DATA_DIR, "docs")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
TRASH_DIR = os.path.join(DATA_DIR, "trash")
SIG_DIR = os.path.join(DATA_DIR, "signatures")
TRASH_RETENTION_SEC = 7 * 86400  # 7 ngày


def p_raw(pid): return os.path.join(PAGES_DIR, f"{pid}_raw.jpg")
def p_warp(pid): return os.path.join(PAGES_DIR, f"{pid}_warp.jpg")
def p_thumb(pid): return os.path.join(PAGES_DIR, f"{pid}_thumb.jpg")
def p_view(pid): return os.path.join(PAGES_DIR, f"{pid}_view.jpg")
def p_meta(pid): return os.path.join(PAGES_DIR, f"{pid}.json")
def d_meta(did): return os.path.join(DOCS_DIR, f"{did}.json")
def t_meta(tid): return os.path.join(TRASH_DIR, f"{tid}.json")


def read_image_utf8(path: str, flags=cv2.IMREAD_COLOR):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            raw_bytes = f.read()
        if not raw_bytes:
            return None
        data = np.frombuffer(raw_bytes, dtype=np.uint8)
        return cv2.imdecode(data, flags)
    except Exception:
        return None


def write_jpg(path: str, img, q: int = 93):
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(q)])
    if ok:
        with open(path, "wb") as f:
            f.write(buf.tobytes())


def write_png(path: str, img):
    ok, buf = cv2.imencode(".png", img)
    if ok:
        with open(path, "wb") as f:
            f.write(buf.tobytes())


def img_to_b64(img_bgr, quality: int = 88) -> str:
    _, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    return base64.b64encode(buf).decode("utf-8")


def file_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def sanitize_filename(name: str, default: str = "Scan") -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name or "").strip(" ._")
    return name[:80] or default


def strip_accents(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def fit_max(img, max_side: int = 1600):
    h, w = img.shape[:2]
    s = max_side / float(max(h, w))
    if s < 1.0:
        return cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    return img


def _download_dir():
    for d in ("/storage/emulated/0/Download", os.path.join(os.path.expanduser("~"), "Downloads")):
        if os.path.isdir(d) and os.access(d, os.W_OK):
            return d
    return None


def _unique(base: str, filename: str) -> str:
    path = os.path.join(base, filename)
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f"{stem} ({n}){ext}"
        n += 1
    return path


def write_output(filename: str, data: bytes) -> str:
    last = None
    for base in [b for b in (_download_dir(), EXPORT_DIR) if b]:
        try:
            path = _unique(base, filename)
            with open(path, "wb") as f:
                f.write(data)
            return path
        except Exception as ex:
            last = ex
    raise IOError(f"Không ghi được file: {last}")


# =====================================================================
# 2. TỰ ĐỘNG TÁCH NỀN BÀN & ĐO CHẤT LƯỢNG ẢNH (MỜ / THIẾU SÁNG)
# =====================================================================
def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def full_corners(w, h):
    return np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype="float32")


def detect_document_quad(img_bgr):
    h, w = img_bgr.shape[:2]
    scale = 500.0 / max(h, w)
    small = cv2.resize(img_bgr, (max(1, int(w * scale)), max(1, int(h * scale))))
    sh, sw = small.shape[:2]
    min_area = (sh * sw) * 0.14

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(gray, 9)
    blur = cv2.GaussianBlur(blur, (5, 5), 0)

    candidates = []
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    closed_otsu = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    cnts1, _ = cv2.findContours(closed_otsu, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates.extend(cnts1)

    v = np.median(blur)
    edged = cv2.Canny(blur, int(max(0, 0.65 * v)), int(min(255, 1.35 * v)))
    closed_canny = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel)
    cnts2, _ = cv2.findContours(closed_canny, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates.extend(cnts2)

    candidates = sorted(candidates, key=cv2.contourArea, reverse=True)[:10]

    for c in candidates:
        area = cv2.contourArea(c)
        if area < min_area or area > (sh * sw * 0.97):
            continue
        hull = cv2.convexHull(c)
        peri = cv2.arcLength(hull, True)
        for eps in [0.015, 0.02, 0.03, 0.04, 0.05]:
            approx = cv2.approxPolyDP(hull, eps * peri, True)
            if len(approx) == 4:
                return order_points(approx.reshape(4, 2) / scale), True
        if area > (sh * sw * 0.25):
            box_pts = cv2.boxPoints(cv2.minAreaRect(hull)) / scale
            return order_points(box_pts), True

    return full_corners(w, h), False


def auto_detect_corners(img_bgr):
    corners, _ = detect_document_quad(img_bgr)
    return corners


def warp_document(img_bgr, corners):
    rect = order_points(np.array(corners, dtype="float32"))
    (tl, tr, br, bl) = rect
    maxW = max(int(np.linalg.norm(br - bl)), int(np.linalg.norm(tr - tl)), 120)
    maxH = max(int(np.linalg.norm(tr - br)), int(np.linalg.norm(tl - bl)), 120)
    dst = np.array([[0, 0], [maxW - 1, 0], [maxW - 1, maxH - 1], [0, maxH - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(img_bgr, M, (maxW, maxH), flags=cv2.INTER_CUBIC)
    if max(maxW, maxH) < 1500:
        f = 1600.0 / max(maxW, maxH)
        warped = cv2.resize(warped, (int(maxW * f), int(maxH * f)), interpolation=cv2.INTER_CUBIC)
    return warped


def analyze_image_quality(img_bgr):
    small = fit_max(img_bgr, 800)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    lum_score = float(np.mean(gray))
    return {
        "blur_score": round(blur_score, 1),
        "lum_score": round(lum_score, 1),
        "is_blur": bool(blur_score < 60.0),
        "is_dark": bool(lum_score < 70.0),
    }


# =====================================================================
# 3. CHỈNH SÁNG, CHE THÔNG TIN, CHÈN CHỮ KÝ & ĐÓNG DẤU MỜ
# =====================================================================
def apply_photoshop_levels(img, brightness: float, contrast: float, gamma: float = 1.0):
    white_point = int(max(135, min(255, 255 - brightness * 1.15)))
    black_point = int(max(0, min(125, contrast * 1.15)))
    if white_point <= black_point + 15:
        white_point = black_point + 15
    span = float(white_point - black_point)
    idx = np.arange(256, dtype=np.float32)
    norm = np.clip((idx - black_point) / span, 0.0, 1.0)
    lut = np.clip((norm ** gamma) * 255.0, 0, 255).astype(np.uint8)
    return cv2.LUT(img, lut)


def smooth_illumination_correct(img_bgr):
    h, w = img_bgr.shape[:2]
    small_w, small_h = max(32, w // 16), max(32, h // 16)
    small = cv2.resize(img_bgr, (small_w, small_h), interpolation=cv2.INTER_AREA)
    bg_small = cv2.medianBlur(small, 15)
    bg_small = cv2.GaussianBlur(bg_small, (25, 25), 0)
    bg_full = cv2.resize(bg_small, (w, h), interpolation=cv2.INTER_CUBIC)
    bg_full = np.maximum(bg_full, 40)
    norm = (img_bgr.astype(np.float32) / bg_full.astype(np.float32)) * 242.0
    return np.clip(norm, 0, 255).astype(np.uint8)


def apply_redactions(img, redactions):
    if not redactions:
        return img
    h, w = img.shape[:2]
    out = img.copy()
    for r in redactions:
        x1 = int(max(0, min(w - 1, float(r.get("x1", 0)) * w)))
        y1 = int(max(0, min(h - 1, float(r.get("y1", 0)) * h)))
        x2 = int(max(0, min(w, float(r.get("x2", 0)) * w)))
        y2 = int(max(0, min(h, float(r.get("y2", 0)) * h)))
        if x2 <= x1 + 2 or y2 <= y1 + 2:
            continue
        mode = r.get("mode", "black")
        if mode == "white":
            out[y1:y2, x1:x2] = 255
        elif mode == "pixel":
            roi = out[y1:y2, x1:x2]
            rh, rw = roi.shape[:2]
            small = cv2.resize(roi, (max(1, rw // 12), max(1, rh // 12)), interpolation=cv2.INTER_LINEAR)
            out[y1:y2, x1:x2] = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)
        else:
            out[y1:y2, x1:x2] = 0
    return out


def extract_signature_rgba(raw_bgr):
    img = fit_max(raw_bgr, 900)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    th = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 15)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)
    coords = cv2.findNonZero(th)
    if coords is not None:
        x, y, w, h = cv2.boundingRect(coords)
        pad = 10
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(img.shape[1], x + w + pad), min(img.shape[0], y + h + pad)
        img = img[y1:y2, x1:x2]
        th = th[y1:y2, x1:x2]
    b, g, r = cv2.split(img)
    b = (b.astype(np.float32) * 0.72).astype(np.uint8)
    g = (g.astype(np.float32) * 0.72).astype(np.uint8)
    r = (r.astype(np.float32) * 0.72).astype(np.uint8)
    alpha = cv2.GaussianBlur(th, (3, 3), 0)
    return cv2.merge([b, g, r, alpha])


def apply_signatures(img, signatures):
    if not signatures:
        return img
    h, w = img.shape[:2]
    out = img.copy()
    for s in signatures:
        fname = s.get("file", "")
        if not fname:
            continue
        spath = os.path.join(SIG_DIR, fname)
        if not os.path.exists(spath):
            continue
        rgba = read_image_utf8(spath, cv2.IMREAD_UNCHANGED)
        if rgba is None or len(rgba.shape) < 3 or rgba.shape[2] < 4:
            continue
        sh, sw = rgba.shape[:2]
        target_w = max(24, int(w * float(s.get("w", 0.28))))
        target_h = max(12, int(target_w * sh / float(max(1, sw))))
        resized = cv2.resize(rgba, (target_w, target_h), interpolation=cv2.INTER_AREA)
        cx = int(float(s.get("x", 0.75)) * w)
        cy = int(float(s.get("y", 0.85)) * h)
        x1, y1 = cx - target_w // 2, cy - target_h // 2
        x2, y2 = x1 + target_w, y1 + target_h
        sx1, sy1 = max(0, -x1), max(0, -y1)
        dx1, dy1 = max(0, x1), max(0, y1)
        dx2, dy2 = min(w, x2), min(h, y2)
        sx2, sy2 = sx1 + (dx2 - dx1), sy1 + (dy2 - dy1)
        if dx2 <= dx1 or dy2 <= dy1:
            continue
        patch = resized[sy1:sy2, sx1:sx2]
        alpha = (patch[:, :, 3:4].astype(np.float32) / 255.0) * float(s.get("opacity", 0.95))
        roi = out[dy1:dy2, dx1:dx2].astype(np.float32)
        blended = patch[:, :, :3].astype(np.float32) * alpha + roi * (1.0 - alpha)
        out[dy1:dy2, dx1:dx2] = np.clip(blended, 0, 255).astype(np.uint8)
    return out


def _find_system_font():
    cands = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "/system/fonts/Roboto-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def apply_watermark(img, wm_text: str, wm_opacity: float = 0.22):
    text = (wm_text or "").strip()
    if not text:
        return img
    h, w = img.shape[:2]
    diag = int(np.hypot(h, w))
    alpha = float(max(0.05, min(0.75, wm_opacity)))

    if HAS_PIL:
        try:
            font_size = max(18, diag // 32)
            fpath = _find_system_font()
            font = PILFont.truetype(fpath, font_size) if fpath else PILFont.load_default()
            layer = PILImage.new("RGBA", (diag, diag), (0, 0, 0, 0))
            draw = PILDraw.Draw(layer)
            step_y = max(font_size * 3, diag // 6)
            step_x = max(font_size * max(8, len(text) // 2 + 2), diag // 2)
            fill_col = (180, 30, 30, int(255 * alpha))
            for y in range(0, diag, step_y):
                offset = (y // step_y) % 2 * (step_x // 2)
                for x in range(-step_x // 2, diag, step_x):
                    draw.text((x + offset, y), text, font=font, fill=fill_col)
            rotated = layer.rotate(32, resample=PILImage.BILINEAR)
            rx, ry = (diag - w) // 2, (diag - h) // 2
            cropped = rotated.crop((rx, ry, rx + w, ry + h))
            base_pil = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")
            merged = PILImage.alpha_composite(base_pil, cropped).convert("RGB")
            return cv2.cvtColor(np.array(merged), cv2.COLOR_RGB2BGR)
        except Exception:
            pass

    ascii_text = strip_accents(text)
    overlay = img.copy()
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 32, 1.0)
    layer = np.full((h, w, 3), 255, dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.uint8)
    scale = max(0.55, min(2.2, diag / 1400.0))
    thick = max(1, int(scale * 2))
    step_y = max(70, h // 5)
    step_x = max(220, w // 2)
    for y in range(-h // 4, int(h * 1.25), step_y):
        for x in range(-w // 4, int(w * 1.25), step_x):
            cv2.putText(layer, ascii_text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (40, 40, 190), thick, cv2.LINE_AA)
            cv2.putText(mask, ascii_text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, 255, thick, cv2.LINE_AA)
    rot_layer = cv2.warpAffine(layer, M, (w, h), borderValue=(255, 255, 255))
    rot_mask = cv2.warpAffine(mask, M, (w, h), borderValue=0) > 10
    blended = cv2.addWeighted(overlay, 1.0 - alpha, rot_layer, alpha, 0)
    overlay[rot_mask] = blended[rot_mask]
    return overlay


def process_page_image(warped_bgr, mode="clear_orig", brightness=38, contrast=35, sharpness=1.0,
                       rotation=0, redactions=None, signatures=None, watermark="", wm_opacity=0.22):
    img = warped_bgr.copy()
    rot = rotation % 360
    if rot == 90:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif rot == 180:
        img = cv2.rotate(img, cv2.ROTATE_180)
    elif rot == 270:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

    if mode == "clear_orig":
        out = apply_photoshop_levels(img, brightness, contrast, 1.05)
    elif mode == "flat_light":
        out = apply_photoshop_levels(smooth_illumination_correct(img), brightness, contrast, 1.1)
    elif mode == "crisp_gray":
        gray = cv2.cvtColor(smooth_illumination_correct(img), cv2.COLOR_BGR2GRAY)
        lev = apply_photoshop_levels(gray, brightness + 10, contrast + 10, 1.15)
        out = cv2.cvtColor(lev, cv2.COLOR_GRAY2BGR)
    elif mode == "bw_print":
        gray = cv2.cvtColor(smooth_illumination_correct(img), cv2.COLOR_BGR2GRAY)
        lev = apply_photoshop_levels(gray, brightness, contrast)
        tv = int(max(110, min(240, 215 - (contrast - brightness) * 0.6)))
        _, bw = cv2.threshold(lev, tv, 255, cv2.THRESH_BINARY)
        out = cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)
    else:
        out = img

    if sharpness > 0.05:
        blur = cv2.GaussianBlur(out, (0, 0), 1.2)
        out = cv2.addWeighted(out, 1.0 + sharpness * 0.6, blur, -sharpness * 0.6, 0)

    if redactions:
        out = apply_redactions(out, redactions)
    if signatures:
        out = apply_signatures(out, signatures)
    if watermark:
        out = apply_watermark(out, watermark, wm_opacity)
    return out


# =====================================================================
# 4. BẢN GHI TRANG, TÀI LIỆU & THÙNG RÁC (7 NGÀY)
# =====================================================================
SETTING_KEYS = (
    "filter", "bright", "contrast", "sharp", "rotation", "selected",
    "redactions", "signatures", "watermark", "wm_opacity",
    "blur_score", "lum_score", "is_blur", "is_dark"
)
DEFAULTS = {
    "filter": "clear_orig", "bright": 38, "contrast": 35, "sharp": 1.0,
    "rotation": 0, "selected": True,
    "redactions": [], "signatures": [], "watermark": "", "wm_opacity": 0.22,
    "blur_score": 120.0, "lum_score": 140.0, "is_blur": False, "is_dark": False,
}

_warp_cache = {}


def get_warped(pg):
    pid = pg["id"]
    if pid in _warp_cache and _warp_cache[pid] is not None:
        return _warp_cache[pid]
    img = read_image_utf8(p_warp(pid))
    if img is None:
        raw = read_image_utf8(p_raw(pid))
        if raw is not None:
            img = fit_max(warp_document(raw, pg["corners"]), 3508)
            write_jpg(p_warp(pid), img, 95)
        else:
            img = np.full((800, 600, 3), 255, dtype=np.uint8)
    _warp_cache[pid] = img
    while len(_warp_cache) > 3:
        _warp_cache.pop(next(iter(_warp_cache)))
    return img


def get_prev(pg):
    if pg.get("prev") is None:
        pg["prev"] = fit_max(get_warped(pg), 900)
    return pg["prev"]


def rebuild_warp(pg, raw=None):
    pid = pg["id"]
    if raw is None:
        raw = read_image_utf8(p_raw(pid))
    if raw is None:
        return
    warped = fit_max(warp_document(raw, pg["corners"]), 3508)
    write_jpg(p_warp(pid), warped, 95)
    _warp_cache[pid] = warped
    while len(_warp_cache) > 3:
        _warp_cache.pop(next(iter(_warp_cache)))
    pg["prev"] = None


def render_page_with_overlay(src_bgr, pg, apply_overlays=True):
    return process_page_image(
        src_bgr,
        pg["filter"],
        pg["bright"],
        pg["contrast"],
        pg["sharp"],
        pg["rotation"],
        pg.get("redactions") if apply_overlays else None,
        pg.get("signatures") if apply_overlays else None,
        pg.get("watermark", "") if apply_overlays else "",
        pg.get("wm_opacity", 0.22),
    )


def refresh_page_render(pg):
    small = render_page_with_overlay(get_prev(pg), pg, apply_overlays=True)
    h, w = small.shape[:2]
    thumb = cv2.resize(small, (220, max(1, int(220 * h / w))), interpolation=cv2.INTER_AREA)
    write_jpg(p_thumb(pg["id"]), thumb, 82)
    write_jpg(p_view(pg["id"]), small, 88)
    pg["thumb_b64"] = img_to_b64(thumb, 82)
    pg["view_b64"] = img_to_b64(small, 88)


def render_full(pg, max_side=None, apply_overlays=True):
    warped = get_warped(pg)
    if max_side:
        warped = fit_max(warped, max_side)
    return render_page_with_overlay(warped, pg, apply_overlays=apply_overlays)


def save_page_meta(pg):
    meta = {k: pg.get(k, DEFAULTS[k]) for k in SETTING_KEYS}
    meta["id"] = pg["id"]
    meta["corners"] = np.asarray(pg["corners"]).tolist()
    meta["name"] = pg.get("name", "")
    with open(p_meta(pg["id"]), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


def natural_key(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text or "")]


def create_page_from_raw(raw_bgr, auto_crop=True, corners=None, name="", **settings):
    pid = uuid.uuid4().hex[:10]
    raw = fit_max(raw_bgr, 3000)
    write_jpg(p_raw(pid), raw, 93)
    q_info = analyze_image_quality(raw)
    if corners is None:
        corners = auto_detect_corners(raw) if auto_crop else full_corners(raw.shape[1], raw.shape[0])
    pg = {
        "id": pid,
        "name": name,
        "corners": np.array(corners, dtype="float32"),
        "prev": None,
        "thumb_b64": "",
        "view_b64": "",
    }
    for k in SETTING_KEYS:
        val = settings.get(k, q_info.get(k, DEFAULTS[k]))
        pg[k] = [dict(x) for x in val] if isinstance(val, list) else val
    rebuild_warp(pg, raw)
    refresh_page_render(pg)
    save_page_meta(pg)
    return pg


def load_page(pid):
    try:
        with open(p_meta(pid), "r", encoding="utf-8") as f:
            meta = json.load(f)
        if not os.path.exists(p_warp(pid)) and not os.path.exists(p_raw(pid)):
            return None
        pg = {
            "id": pid,
            "name": meta.get("name", ""),
            "corners": np.array(meta["corners"], dtype="float32"),
            "prev": None,
            "thumb_b64": "",
            "view_b64": "",
        }
        for k in SETTING_KEYS:
            val = meta.get(k, DEFAULTS[k])
            pg[k] = [dict(x) for x in val] if isinstance(val, list) else val
        if os.path.exists(p_thumb(pid)) and os.path.exists(p_view(pid)):
            pg["thumb_b64"] = file_to_b64(p_thumb(pid))
            pg["view_b64"] = file_to_b64(p_view(pid))
        else:
            refresh_page_render(pg)
        return pg
    except Exception:
        return None


def delete_page_files(pg_or_pid):
    pid = pg_or_pid["id"] if isinstance(pg_or_pid, dict) else str(pg_or_pid)
    _warp_cache.pop(pid, None)
    for p in (p_raw(pid), p_warp(pid), p_thumb(pid), p_view(pid), p_meta(pid)):
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def save_doc(doc):
    data = {
        "id": doc["id"],
        "title": doc["title"],
        "folder": doc.get("folder", "Chung") or "Chung",
        "date": doc["date"],
        "selected": doc.get("selected", False),
        "page_ids": [pg["id"] for pg in doc["pages"]],
    }
    with open(d_meta(doc["id"]), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def delete_doc_json(doc):
    try:
        if os.path.exists(d_meta(doc["id"])):
            os.remove(d_meta(doc["id"]))
    except OSError:
        pass


def new_doc_record(title, pages, folder="Chung"):
    return {
        "id": str(int(time.time() * 1000)),
        "title": title,
        "folder": folder or "Chung",
        "date": time.strftime("%d/%m/%Y %H:%M"),
        "selected": False,
        "pages": pages,
        "undo": [],
    }


def load_all_docs():
    docs = []
    if not os.path.isdir(DOCS_DIR):
        return docs
    for fn in os.listdir(DOCS_DIR):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(DOCS_DIR, fn), "r", encoding="utf-8") as f:
                d = json.load(f)
            pages = [pg for pg in (load_page(pid) for pid in d.get("page_ids", [])) if pg]
            if not pages:
                continue
            docs.append({
                "id": str(d["id"]),
                "title": d.get("title", "Tài liệu"),
                "folder": d.get("folder", "Chung") or "Chung",
                "date": d.get("date", ""),
                "selected": bool(d.get("selected", False)),
                "pages": pages,
                "undo": [],
            })
        except Exception:
            continue
    docs.sort(key=lambda d: int(d["id"]) if str(d["id"]).isdigit() else 0, reverse=True)
    return docs


# --- Thùng rác 7 ngày ---
def move_doc_to_trash(doc):
    tid = f"doc_{doc['id']}_{int(time.time() * 1000)}"
    rec = {
        "tid": tid,
        "type": "doc",
        "deleted_at": time.time(),
        "title": doc["title"],
        "folder": doc.get("folder", "Chung"),
        "doc_id": doc["id"],
        "date": doc["date"],
        "page_ids": [pg["id"] for pg in doc["pages"]],
    }
    with open(t_meta(tid), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
    delete_doc_json(doc)


def move_pages_to_trash(doc, pages):
    tid = f"pages_{doc['id']}_{int(time.time() * 1000)}"
    rec = {
        "tid": tid,
        "type": "pages",
        "deleted_at": time.time(),
        "title": f"{len(pages)} trang từ '{doc['title']}'",
        "folder": doc.get("folder", "Chung"),
        "doc_id": doc["id"],
        "doc_title": doc["title"],
        "page_ids": [pg["id"] for pg in pages],
    }
    with open(t_meta(tid), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)


def purge_and_load_trash():
    now = time.time()
    items = []
    if not os.path.isdir(TRASH_DIR):
        return items
    for fn in os.listdir(TRASH_DIR):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(TRASH_DIR, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                rec = json.load(f)
            age = now - float(rec.get("deleted_at", now))
            if age > TRASH_RETENTION_SEC:
                for pid in rec.get("page_ids", []):
                    delete_page_files(pid)
                os.remove(path)
            else:
                rec["days_left"] = max(1, int(np.ceil((TRASH_RETENTION_SEC - age) / 86400.0)))
                items.append(rec)
        except Exception:
            continue
    items.sort(key=lambda r: r.get("deleted_at", 0), reverse=True)
    return items


def delete_trash_item_permanently(rec):
    for pid in rec.get("page_ids", []):
        delete_page_files(pid)
    try:
        if os.path.exists(t_meta(rec["tid"])):
            os.remove(t_meta(rec["tid"]))
    except OSError:
        pass


# --- Sao lưu & Khôi phục toàn bộ (.zip) ---
def create_full_backup_zip() -> str:
    fn = f"CSScanner_Backup_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    buf_path = os.path.join(tempfile.gettempdir(), fn)
    with zipfile.ZipFile(buf_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in ("docs", "pages", "trash", "signatures"):
            subdir = os.path.join(DATA_DIR, sub)
            if not os.path.isdir(subdir):
                continue
            for root, _, files in os.walk(subdir):
                for file in files:
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, DATA_DIR).replace("\\", "/")
                    zf.write(full_p, rel_p)
    with open(buf_path, "rb") as f:
        data = f.read()
    try:
        os.remove(buf_path)
    except OSError:
        pass
    return write_output(fn, data)


def restore_full_backup_zip(zip_path: str) -> int:
    if not zip_path or not os.path.exists(zip_path):
        raise ValueError("Không tìm thấy file ZIP đã chọn!")
    with zipfile.ZipFile(zip_path, "r") as zf:
        count_extracted = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            norm_name = info.filename.replace("\\", "/").lstrip("/")
            parts = norm_name.split("/")
            if len(parts) >= 2 and parts[0] in ("docs", "pages", "trash", "signatures"):
                dest_dir = os.path.join(DATA_DIR, parts[0])
                os.makedirs(dest_dir, exist_ok=True)
                dest_file = os.path.join(dest_dir, os.path.basename(norm_name))
                with zf.open(info, "r") as src, open(dest_file, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                count_extracted += 1
        if count_extracted == 0:
            raise ValueError("File ZIP không chứa dữ liệu sao lưu hợp lệ của CS Scanner!")
    _warp_cache.clear()
    return len(load_all_docs())


# --- Hoàn tác ---
def snapshot_doc(doc):
    snap = []
    for pg in doc["pages"]:
        st = {}
        for k in SETTING_KEYS:
            val = pg.get(k, DEFAULTS[k])
            st[k] = [dict(x) for x in val] if isinstance(val, list) else val
        st["corners"] = np.asarray(pg["corners"]).tolist()
        snap.append((pg["id"], st))
    doc["undo"].append(snap)
    if len(doc["undo"]) > 15:
        doc["undo"].pop(0)


def restore_snapshot(doc, snap):
    by_id = {pg["id"]: pg for pg in doc["pages"]}
    new_pages = []
    for pid, st in snap:
        pg = by_id.get(pid)
        if pg is None:
            continue
        new_c = np.array(st["corners"], dtype="float32")
        changed = not np.allclose(new_c, pg["corners"], atol=0.5)
        for k in SETTING_KEYS:
            val = st.get(k, DEFAULTS[k])
            pg[k] = [dict(x) for x in val] if isinstance(val, list) else val
        pg["corners"] = new_c
        if changed:
            rebuild_warp(pg)
        refresh_page_render(pg)
        save_page_meta(pg)
        new_pages.append(pg)
    have = {p["id"] for p in new_pages}
    new_pages.extend(pg for pg in doc["pages"] if pg["id"] not in have)
    doc["pages"] = new_pages
    save_doc(doc)


# =====================================================================
# 5. XUẤT FILE: PDF A4 + NÉN THEO DUNG LƯỢNG MỤC TIÊU + GHÉP 2/4/6 TRANG
# =====================================================================
QUALITY = {"low": (150, 78), "mid": (200, 86), "high": (300, 92)}


def compose_pdf_page(img, dpi, paper):
    ih, iw = img.shape[:2]
    a4w, a4h = int(round(8.2677 * dpi)), int(round(11.693 * dpi))
    if iw > ih:
        a4w, a4h = a4h, a4w
    if paper == "a4":
        s = min(a4w / float(iw), a4h / float(ih))
        nw, nh = max(1, int(iw * s)), max(1, int(ih * s))
        r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        canvas = np.full((a4h, a4w, 3), 255, np.uint8)
        y, x = (a4h - nh) // 2, (a4w - nw) // 2
        canvas[y:y + nh, x:x + nw] = r
        return canvas
    s = max(a4w, a4h) / float(max(iw, ih))
    return cv2.resize(img, (max(1, int(iw * s)), max(1, int(ih * s))),
                      interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)


def build_pdf(items):
    n = len(items)
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}

    def add(num, body):
        offsets[num] = len(out)
        out.extend(f"{num} 0 obj\n".encode())
        out.extend(body)
        out.extend(b"\nendobj\n")

    kids = " ".join(f"{3 + 3 * i} 0 R" for i in range(n))
    add(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    add(2, f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    for i, (jpg, w, h, dpi) in enumerate(items):
        pn, cn, im = 3 + 3 * i, 4 + 3 * i, 5 + 3 * i
        pw, ph = w * 72.0 / dpi, h * 72.0 / dpi
        add(pn, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:.2f} {ph:.2f}] "
                 f"/Resources << /XObject << /Im0 {im} 0 R >> >> /Contents {cn} 0 R >>").encode())
        content = f"q {pw:.2f} 0 0 {ph:.2f} 0 0 cm /Im0 Do Q".encode()
        add(cn, f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream")
        add(im, (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB "
                 f"/BitsPerComponent 8 /Filter /DCTDecode /Length {len(jpg)} >>\nstream\n").encode()
            + jpg + b"\nendstream")
    xref = len(out)
    size = 3 * n + 3
    out.extend(f"xref\n0 {size}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for num in range(1, size):
        out.extend(f"{offsets[num]:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(out)


def build_pdf_with_target_mb(rendered_imgs, paper, base_dpi, base_q, max_mb=None):
    if not max_mb or max_mb <= 0:
        items = []
        for im in rendered_imgs:
            canvas = compose_pdf_page(im, base_dpi, paper)
            ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), base_q])
            h, w = canvas.shape[:2]
            items.append((buf.tobytes(), w, h, base_dpi))
        return build_pdf(items)

    target_bytes = int(max_mb * 1024 * 1024 * 0.97)
    steps = [
        (base_dpi, base_q),
        (min(base_dpi, 220), min(base_q, 82)),
        (180, 75),
        (150, 68),
        (130, 60),
        (110, 52),
        (95, 45),
        (80, 38),
        (65, 32),
        (55, 25),
    ]
    last_pdf = b""
    for dpi, q in steps:
        items = []
        for im in rendered_imgs:
            canvas = compose_pdf_page(im, dpi, paper)
            ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), q])
            b = buf.tobytes()
            h, w = canvas.shape[:2]
            items.append((b, w, h, dpi))
        last_pdf = build_pdf(items)
        if len(last_pdf) <= target_bytes:
            return last_pdf
    return last_pdf


def export_pages(pages, name, fmt, quality, paper, max_mb=None):
    dpi, q = QUALITY.get(quality, QUALITY["mid"])
    base = sanitize_filename(name)
    rendered = [render_full(pg) for pg in pages]
    if fmt == "pdf":
        pdf_bytes = build_pdf_with_target_mb(rendered, paper, dpi, q, max_mb=max_mb)
        return [write_output(base + ".pdf", pdf_bytes)]
    paths = []
    for i, im in enumerate(rendered):
        ok, buf = cv2.imencode(".jpg", im, [int(cv2.IMWRITE_JPEG_QUALITY), min(98, q + 6)])
        fn = f"{base}.jpg" if len(rendered) == 1 else f"{base}_{i + 1}.jpg"
        paths.append(write_output(fn, buf.tobytes()))
    return paths


def compose_multi_grid_a4(imgs, layout=2, dpi=200):
    W, H = int(round(8.2677 * dpi)), int(round(11.693 * dpi))
    canvas = np.full((H, W, 3), 255, np.uint8)
    if layout <= 2:
        rows, cols = 2, 1
    elif layout <= 4:
        rows, cols = 2, 2
    else:
        rows, cols = 3, 2

    margin_x, margin_y = int(W * 0.05), int(H * 0.04)
    gap_x, gap_y = int(W * 0.03), int(H * 0.025)
    cell_w = (W - 2 * margin_x - (cols - 1) * gap_x) // cols
    cell_h = (H - 2 * margin_y - (rows - 1) * gap_y) // rows

    for idx, im in enumerate(imgs[:rows * cols]):
        r_idx, c_idx = idx // cols, idx % cols
        ih, iw = im.shape[:2]
        s = min(cell_w / float(iw), cell_h / float(ih))
        nw, nh = max(1, int(iw * s)), max(1, int(ih * s))
        resized = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        cx = margin_x + c_idx * (cell_w + gap_x) + (cell_w - nw) // 2
        cy = margin_y + r_idx * (cell_h + gap_y) + (cell_h - nh) // 2
        canvas[cy:cy + nh, cx:cx + nw] = resized
        cv2.rectangle(canvas, (cx, cy), (cx + nw - 1, cy + nh - 1), (175, 175, 175), 2)
    return canvas


# =====================================================================
# 6. GIAO DIỆN ĐIỆN THOẠI (MOBILE-FIRST UI)
# =====================================================================
def main(page: ft.Page):
    page.title = "CS Scanner Pro V6.4"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.bgcolor = "#EEF2F5"
    try:
        page.window.width = 430
        page.window.height = 880
    except Exception:
        pass

    CS_TEAL, CS_DARK, CS_ACCENT, CS_ORANGE = "#00897B", "#182026", "#00BFA5", "#E65100"
    WHITE = Colors.WHITE

    app_data = {
        "docs": [],
        "trash": [],
        "current_doc_idx": -1,
        "active_page_idx": 0,
        "studio_tab": "color",  # color | crop | secure
        "crop_target_idx": -1,
        "crop_raw": None,
        "crop_disp": None,
        "search_query": "",
        "active_folder": "Tất cả",
        "sort_mode": "date_desc",
        "busy": False,
        "pending": None,
        "picker_mode": "import_images",
        "cam_running": False,
    }
    try:
        app_data["docs"] = load_all_docs()
        app_data["trash"] = purge_and_load_trash()
    except Exception:
        app_data["docs"] = []
        app_data["trash"] = []

    root_body = ft.Container(expand=True)
    busy_bar = ft.ProgressBar(visible=False, color=CS_ACCENT, height=3)

    FILTER_OPTIONS = [
        ("clear_orig", "🌟 Sáng Rõ"),
        ("flat_light", "☀️ Khử Bóng"),
        ("crisp_gray", "📄 Chữ Nét"),
        ("bw_print", "⚫ Đen Trắng"),
        ("raw", "🖼️ Ảnh Gốc"),
    ]

    def cur_doc():
        return app_data["docs"][app_data["current_doc_idx"]]

    def mobile_action_tile(icon_name, label, on_tap, bg="#F5F7F9", fg="#263238", icon_col=CS_TEAL, expand_tile=True):
        return ft.Container(
            expand=expand_tile,
            bgcolor=bg,
            padding=pad_sym(6, 8),
            border_radius=10,
            border=border_all(1, "#CFD8DC"),
            alignment=ALIGN_CENTER,
            on_click=on_tap,
            content=ft.Column([
                ft.Icon(icon_name, color=icon_col, size=22),
                ft.Text(label, size=11, weight=ft.FontWeight.BOLD, color=fg,
                        text_align=ft.TextAlign.CENTER, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ], spacing=3, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        )

    # ---------- Thông báo / Hộp thoại (Tương thích cả Flet 0.21, 0.25 và 0.70+) ----------
    def toast(msg, color=CS_TEAL):
        sb = ft.SnackBar(content=ft.Text(msg, color=WHITE, weight=ft.FontWeight.BOLD, size=13),
                         bgcolor=color, duration=2800)
        if hasattr(page, "open"):
            try:
                page.open(sb)
                return
            except Exception:
                pass
        if hasattr(page, "show_dialog"):
            try:
                page.show_dialog(sb)
                return
            except Exception:
                pass
        page.snack_bar = sb
        sb.open = True
        page.update()

    def open_dlg(dlg):
        if hasattr(page, "open"):
            try:
                page.open(dlg)
                return
            except Exception:
                pass
        if hasattr(page, "show_dialog"):
            try:
                page.show_dialog(dlg)
                return
            except Exception:
                pass
        if dlg not in page.overlay:
            page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def close_dlg(dlg):
        if hasattr(page, "close"):
            try:
                page.close(dlg)
                return
            except Exception:
                pass
        if hasattr(page, "pop_dialog"):
            try:
                page.pop_dialog()
                return
            except Exception:
                pass
        dlg.open = False
        page.update()
        if dlg in page.overlay:
            page.overlay.remove(dlg)

    def confirm_dlg(title, msg, on_yes, yes_label="Đồng ý"):
        def yes(e):
            close_dlg(dlg)
            on_yes()
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(title, size=16, weight=ft.FontWeight.BOLD), content=ft.Text(msg, size=13),
            actions=[ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                     Btn(yes_label, bgcolor=Colors.RED_600, color=WHITE, on_click=yes)])
        open_dlg(dlg)

    # ---------- Chạy nền ----------
    def run_bg(work, done=None, latest_wins=False):
        if app_data["busy"]:
            if latest_wins:
                app_data["pending"] = (work, done)
            else:
                toast("⏳ Đang xử lý, vui lòng đợi...", Colors.ORANGE_800)
            return
        app_data["busy"] = True

        def _t():
            busy_bar.visible = True
            try:
                page.update()
            except Exception:
                pass
            res, err = None, None
            try:
                res = work()
            except Exception as ex:
                err = ex
            app_data["busy"] = False
            busy_bar.visible = False
            try:
                if err is not None:
                    toast(f"❌ Lỗi: {err}", Colors.RED_700)
                elif done:
                    done(res)
            except Exception as ex:
                toast(f"❌ Lỗi giao diện: {ex}", Colors.RED_700)
            try:
                page.update()
            except Exception:
                pass
            nxt, app_data["pending"] = app_data["pending"], None
            if nxt:
                run_bg(nxt[0], nxt[1], True)

        threading.Thread(target=_t, daemon=True).start()

    # ---------- Chia sẻ trên Android (Flet 0.70+ Share Service) hoặc Mở thư mục trên Windows ----------
    share_svc = None
    if hasattr(ft, "Share"):
        try:
            share_svc = ft.Share()
            if hasattr(page, "services"):
                page.services.append(share_svc)
        except Exception:
            share_svc = None

    def share_or_reveal_files(paths):
        if not paths:
            return
        first_path = paths[0]
        if os.name == "nt" and os.path.exists(first_path):
            try:
                os.system(f'explorer /select,"{os.path.normpath(first_path)}"')
                toast(f"📂 Đã lưu & mở thư mục: {os.path.basename(first_path)}", CS_TEAL)
                return
            except Exception:
                pass

        if share_svc is not None and hasattr(ft, "ShareFile"):
            tmp = os.path.join(os.environ.get("FLET_APP_STORAGE_TEMP") or tempfile.gettempdir(), "cs_share")

            async def _do_share():
                try:
                    os.makedirs(tmp, exist_ok=True)
                    s_files = []
                    for p in paths:
                        dst = os.path.join(tmp, os.path.basename(p))
                        shutil.copyfile(p, dst)
                        s_files.append(ft.ShareFile.from_path(dst))
                    await share_svc.share_files(s_files, text="Tài liệu scan từ CS Scanner Pro")
                except Exception:
                    toast(f"✅ Đã lưu tại: {first_path}", CS_TEAL)

            try:
                page.run_task(_do_share)
                return
            except Exception:
                pass

        toast(f"✅ Đã lưu tại: {first_path}", CS_TEAL)

    # ---------- Đổi tên & Đổi Thư mục ----------
    def rename_doc_dialog(doc_idx, after):
        doc = app_data["docs"][doc_idx]
        tf_name = ft.TextField(value=doc["title"], label="Tên tài liệu", autofocus=True)
        existing_folders = sorted({d.get("folder", "Chung") or "Chung" for d in app_data["docs"]}
                                  | {"Chung", "Hồ sơ", "CCCD", "Hóa đơn", "Giáo án"})
        tf_folder = ft.TextField(value=doc.get("folder", "Chung"), label="Thư mục")
        folder_chips = ft.Row(
            scroll=ft.ScrollMode.AUTO,
            spacing=4,
            controls=[
                ft.TextButton(f"📁 {fd}", on_click=lambda e, f=fd: (setattr(tf_folder, "value", f), page.update()))
                for fd in existing_folders
            ],
        )

        def save(e):
            name = (tf_name.value or "").strip()
            folder = (tf_folder.value or "").strip() or "Chung"
            if not name:
                tf_name.error_text = "Tên không được để trống"
                page.update()
                return
            doc["title"] = name
            doc["folder"] = folder
            save_doc(doc)
            close_dlg(dlg)
            after()
            toast(f"✏️ Đã lưu: {name}")

        tf_name.on_submit = save
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("✏️ Đổi tên & Thư mục", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column([tf_name, tf_folder, folder_chips], tight=True, spacing=6),
            actions=[ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                     Btn("Lưu", bgcolor=CS_TEAL, color=WHITE, on_click=save)])
        open_dlg(dlg)

    # ---------- Xuất file (Nén PDF theo dung lượng MB) ----------
    def open_export_dialog(default_name, pages, fmt):
        pages = list(pages)
        if not pages:
            toast("⚠️ Không có trang nào để xuất!", Colors.ORANGE_800)
            return
        ext = ".pdf" if fmt == "pdf" else ".jpg"
        tf = ft.TextField(value=default_name, label=f"Tên file ({ext})", autofocus=True,
                          **({"suffix": ext} if NEW_FLET else {"suffix_text": ext}))
        dd_q = ft.Dropdown(label="Chất lượng", value="mid", options=[
            DDOpt(key="low", text="Nhỏ gọn · 150 DPI (Zalo/Email)"),
            DDOpt(key="mid", text="Cân bằng · 200 DPI"),
            DDOpt(key="high", text="Cao · 300 DPI (In rõ nét)")])
        dd_p = ft.Dropdown(label="Khổ giấy PDF", value="a4", options=[
            DDOpt(key="a4", text="Khổ A4 chuẩn (Căn giữa)"),
            DDOpt(key="fit", text="Vừa khít khung ảnh")])
        tf_mb = ft.TextField(
            value="",
            label="Nén dưới số MB (Bỏ trống = Không giới hạn)",
            hint_text="VD: 2 hoặc 5",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        quick_mb_row = ft.Row([
            ft.TextButton("<= 1MB", on_click=lambda _: (setattr(tf_mb, "value", "1"), page.update())),
            ft.TextButton("<= 2MB", on_click=lambda _: (setattr(tf_mb, "value", "2"), page.update())),
            ft.TextButton("<= 5MB", on_click=lambda _: (setattr(tf_mb, "value", "5"), page.update())),
            ft.TextButton("Tắt nén", on_click=lambda _: (setattr(tf_mb, "value", ""), page.update())),
        ], scroll=ft.ScrollMode.AUTO, spacing=0)

        controls = [tf, dd_q]
        if fmt == "pdf":
            controls.extend([dd_p, tf_mb, quick_mb_row])
        controls.append(ft.Text(f"Tổng cộng: {len(pages)} trang", size=11, color="#546E7A"))

        def do(share_after):
            name = (tf.value or "").strip()
            if not name:
                tf.error_text = "Hãy nhập tên file"
                page.update()
                return
            max_mb = None
            raw_mb = (tf_mb.value or "").strip().replace(",", ".")
            if fmt == "pdf" and raw_mb:
                try:
                    max_mb = float(raw_mb)
                    if max_mb <= 0:
                        raise ValueError()
                except ValueError:
                    tf_mb.error_text = "Nhập số MB hợp lệ"
                    page.update()
                    return

            q, paper = dd_q.value or "mid", dd_p.value or "a4"
            close_dlg(dlg)

            def done(paths):
                mb = sum(os.path.getsize(p) for p in paths) / 1048576.0
                if share_after:
                    share_or_reveal_files(paths)
                else:
                    toast(f"✅ Đã lưu ({mb:.2f} MB): {os.path.basename(paths[0])}")

            run_bg(lambda: export_pages(pages, name, fmt, q, paper, max_mb=max_mb), done)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("📄 Xuất file PDF" if fmt == "pdf" else "🖼️ Xuất ảnh JPG", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column(controls, tight=True, spacing=6),
            actions=[ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                     OutBtn("💾 Lưu", on_click=lambda _: do(False)),
                     Btn("📤 Lưu & Chia sẻ", bgcolor=CS_TEAL, color=WHITE, on_click=lambda _: do(True))],
            actions_alignment=ft.MainAxisAlignment.END)
        open_dlg(dlg)

    def export_selected_docs_pdf(e=None):
        sel = [d for d in app_data["docs"] if d.get("selected")]
        if not sel:
            toast("⚠️ Hãy tích chọn ít nhất 1 tài liệu!", Colors.ORANGE_800)
            return
        pages = [pg for d in sel for pg in d["pages"]]
        default = sel[0]["title"] if len(sel) == 1 else f"Scan_{time.strftime('%Y%m%d_%H%M')}"
        open_export_dialog(default, pages, "pdf")

    def export_current_doc_pdf(e=None):
        d = cur_doc()
        open_export_dialog(d["title"], d["pages"], "pdf")

    def export_current_doc_jpgs(e=None):
        d = cur_doc()
        open_export_dialog(d["title"], d["pages"], "jpg")

    # =================================================================
    # HỘP THOẠI THÙNG RÁC (LƯU 7 NGÀY) & SAO LƯU (.ZIP)
    # =================================================================
    def open_trash_dialog(e=None):
        app_data["trash"] = purge_and_load_trash()
        trash_col = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, height=320)

        def rebuild_trash_list():
            trash_col.controls.clear()
            if not app_data["trash"]:
                trash_col.controls.append(
                    ft.Container(height=200, alignment=ALIGN_CENTER,
                                 content=ft.Text("Thùng rác trống (Tự xóa sau 7 ngày)", color="#78909C", size=12))
                )
            else:
                for rec in list(app_data["trash"]):
                    kind = "📁 Bộ" if rec.get("type") == "doc" else "📄 Trang"
                    sub = f"{kind} • Còn {rec.get('days_left', 7)} ngày • {len(rec.get('page_ids', []))} trang"
                    trash_col.controls.append(ft.Card(content=ft.Container(padding=8, content=ft.Row([
                        ft.Column([
                            ft.Text(rec.get("title", "Mục đã xóa"), weight=ft.FontWeight.BOLD, size=12, max_lines=1),
                            ft.Text(sub, size=10, color="#546E7A"),
                        ], expand=True, spacing=2),
                        OutBtn("♻️ Lấy lại", on_click=lambda ev, r=rec: restore_item(r)),
                        ft.IconButton(Icons.DELETE_FOREVER, icon_color=Colors.RED_700,
                                      on_click=lambda ev, r=rec: kill_item(r)),
                    ]))))
            page.update()

        def restore_item(rec):
            pages = [pg for pg in (load_page(pid) for pid in rec.get("page_ids", [])) if pg]
            if not pages:
                delete_trash_item_permanently(rec)
                app_data["trash"] = purge_and_load_trash()
                rebuild_trash_list()
                toast("⚠️ Không tìm thấy file ảnh gốc!", Colors.ORANGE_800)
                return

            if rec.get("type") == "doc":
                existing_ids = {d["id"] for d in app_data["docs"]}
                restored_id = str(rec.get("doc_id") or int(time.time() * 1000))
                if restored_id in existing_ids:
                    restored_id = str(int(time.time() * 1000))
                nd = {
                    "id": restored_id,
                    "title": rec.get("title", "Tài liệu khôi phục"),
                    "folder": rec.get("folder", "Chung"),
                    "date": rec.get("date") or time.strftime("%d/%m/%Y %H:%M"),
                    "selected": False,
                    "pages": pages,
                    "undo": [],
                }
                app_data["docs"].insert(0, nd)
                save_doc(nd)
            else:
                target = next((d for d in app_data["docs"] if str(d["id"]) == str(rec.get("doc_id"))), None)
                if target is not None:
                    target["pages"].extend(pages)
                    save_doc(target)
                else:
                    nd = new_doc_record(rec.get("doc_title") or "Trang khôi phục", pages, rec.get("folder", "Chung"))
                    app_data["docs"].insert(0, nd)
                    save_doc(nd)

            try:
                if os.path.exists(t_meta(rec["tid"])):
                    os.remove(t_meta(rec["tid"]))
            except OSError:
                pass
            app_data["trash"] = purge_and_load_trash()
            rebuild_trash_list()
            render_home_view()
            toast("♻️ Đã khôi phục!")

        def kill_item(rec):
            delete_trash_item_permanently(rec)
            app_data["trash"] = purge_and_load_trash()
            rebuild_trash_list()
            render_home_view()

        def empty_all(_):
            for r in list(app_data["trash"]):
                delete_trash_item_permanently(r)
            app_data["trash"] = []
            close_dlg(dlg)
            render_home_view()
            toast("🗑️ Đã dọn sạch thùng rác!")

        rebuild_trash_list()
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"🗑️ Thùng rác ({len(app_data['trash'])})", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(width=360, content=trash_col),
            actions=[
                ft.TextButton("🔥 Xóa sạch", on_click=empty_all),
                Btn("Đóng", bgcolor=CS_TEAL, color=WHITE, on_click=lambda _: close_dlg(dlg)),
            ],
        )
        open_dlg(dlg)

    def open_backup_dialog(e=None):
        def do_backup(_):
            close_dlg(dlg)
            run_bg(create_full_backup_zip, lambda path: share_or_reveal_files([path]))

        def do_restore(_):
            close_dlg(dlg)
            app_data["picker_mode"] = "restore_zip"
            pick_files_generic(allow_multiple=False, file_type=ft.FilePickerFileType.ANY)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("💾 Sao lưu & Khôi phục (.ZIP)", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.Text("• Sao lưu: Xuất toàn bộ tài liệu, ảnh gốc, chữ ký ra 1 file .ZIP để lưu lên Drive.", size=12),
                ft.Text("• Khôi phục: Nhập lại file .ZIP khi cài lại app hoặc đổi điện thoại/máy tính.", size=12),
            ], tight=True, spacing=8),
            actions=[
                ft.TextButton("Đóng", on_click=lambda _: close_dlg(dlg)),
                OutBtn("📥 Nhập .ZIP", on_click=do_restore),
                Btn("📤 Xuất .ZIP", bgcolor=CS_TEAL, color=WHITE, on_click=do_backup),
            ],
        )
        open_dlg(dlg)

    # =================================================================
    # MÀN HÌNH XEM TRƯỚC TOÀN MÀN HÌNH (FULLSCREEN INSPECT)
    # =================================================================
    pv = {"idx": 0, "compare": False}
    pv_holder = ft.Container(expand=True, bgcolor="#0D1214", alignment=ALIGN_CENTER)
    pv_img = make_img(fit=FIT.CONTAIN)
    pv_title = ft.Text("", color=WHITE, size=14, weight=ft.FontWeight.BOLD, expand=True)
    pv_compare_btn = OutBtn("👁 So sánh Ảnh Gốc")

    def render_preview_b64(pg, compare):
        warped = fit_max(get_warped(pg), 1500)
        if compare:
            src = process_page_image(warped, "raw", 0, 0, 0.0, pg["rotation"])
        else:
            src = render_page_with_overlay(warped, pg, apply_overlays=True)
        return img_to_b64(src, 92)

    def pv_render(reset_zoom=False):
        doc = cur_doc()
        pages = doc["pages"]
        pv["idx"] = max(0, min(pv["idx"], len(pages) - 1))
        pg = pages[pv["idx"]]
        tag = " [GỐC]" if pv["compare"] else ""
        pv_title.value = f"Trang {pv['idx'] + 1}/{len(pages)}{tag}"
        set_btn_text(pv_compare_btn, "👁 Đang xem: Ảnh Gốc" if pv["compare"] else "👁 So sánh Ảnh Gốc")
        if reset_zoom or pv_holder.content is None:
            pv_holder.content = ft.InteractiveViewer(min_scale=1, max_scale=5, content=pv_img)
        page.update()
        compare = pv["compare"]

        def done(b64):
            set_img(pv_img, b64)
            page.update()

        run_bg(lambda: render_preview_b64(pg, compare), done, latest_wins=True)

    def pv_goto(i):
        doc = cur_doc()
        pv["idx"] = max(0, min(i, len(doc["pages"]) - 1))
        pv["compare"] = False
        pv_render(reset_zoom=True)

    def close_preview(e=None):
        app_data["active_page_idx"] = pv["idx"]
        open_doc_studio(app_data["current_doc_idx"], keep_page=True)

    pv_compare_btn.on_click = lambda e: (pv.update({"compare": not pv["compare"]}), pv_render())

    def open_preview(p_idx):
        page.floating_action_button = None
        root_body.content = ft.Column([
            ft.Container(bgcolor="#11171A", padding=pad_sym(8, 6), content=ft.Row([
                ft.IconButton(Icons.ARROW_BACK, icon_color=WHITE, on_click=close_preview),
                pv_title,
                ft.IconButton(Icons.CHEVRON_LEFT, icon_color=WHITE, on_click=lambda _: pv_goto(pv["idx"] - 1)),
                ft.IconButton(Icons.CHEVRON_RIGHT, icon_color=WHITE, on_click=lambda _: pv_goto(pv["idx"] + 1)),
            ])),
            pv_holder,
            ft.Container(bgcolor="#182026", padding=pad_sym(14, 10), content=ft.Row([
                ft.Text("Chụm 2 ngón tay để phóng to kiểm tra chữ", size=11, color="#B0BEC5", expand=True),
                pv_compare_btn,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)),
        ], expand=True, spacing=0)
        pv_goto(p_idx)

    # =================================================================
    # MÀN HÌNH 1: TRANG CHỦ ĐIỆN THOẠI (BOTTOM ACTION BAR + CONTEXT BAR)
    # =================================================================
    docs_list_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    def toggle_all_docs(state):
        for d in app_data["docs"]:
            d["selected"] = state
            save_doc(d)
        render_home_view()

    def delete_selected_docs(e=None):
        sel = [d for d in app_data["docs"] if d.get("selected")]
        if not sel:
            toast("⚠️ Chưa tích chọn tài liệu nào!", Colors.ORANGE_800)
            return

        def go():
            for d in sel:
                move_doc_to_trash(d)
            app_data["docs"] = [d for d in app_data["docs"] if not d.get("selected")]
            app_data["trash"] = purge_and_load_trash()
            render_home_view()
            toast(f"🗑️ Đã chuyển {len(sel)} tài liệu vào Thùng rác!")

        confirm_dlg("Bỏ vào Thùng rác?", f"Chuyển {len(sel)} bộ tài liệu vào Thùng rác (giữ 7 ngày)?", go, "Xóa")

    def merge_selected_docs(e=None):
        sel = [d for d in app_data["docs"] if d.get("selected")]
        if len(sel) < 2:
            toast("⚠️ Hãy tích chọn ít nhất 2 tài liệu để gộp!", Colors.ORANGE_800)
            return
        combined = [pg for d in sel for pg in d["pages"]]
        nd = new_doc_record("Tài liệu gộp", combined, folder=sel[0].get("folder", "Chung"))
        for d in sel:
            delete_doc_json(d)
        app_data["docs"] = [d for d in app_data["docs"] if not d.get("selected")]
        app_data["docs"].insert(0, nd)
        save_doc(nd)
        render_home_view()
        toast(f"📑 Đã gộp thành 1 bộ ({len(combined)} trang)!")

    def open_batch_dialog(e=None):
        sel = [d for d in app_data["docs"] if d.get("selected")]
        if not sel:
            toast("Hãy tích chọn ít nhất 1 tài liệu!", Colors.ORANGE_800)
            return
        dd = ft.Dropdown(label="Bộ lọc màu", value="clear_orig",
                         options=[DDOpt(key=k, text=v) for k, v in FILTER_OPTIONS])
        sb = ft.Slider(min=0, max=85, divisions=17, value=38, label="Sáng nền: {value}")
        sc = ft.Slider(min=0, max=85, divisions=17, value=35, label="Đậm chữ: {value}")

        def apply(_):
            f, b, c = dd.value or "clear_orig", int(sb.value), int(sc.value)
            close_dlg(dlg)

            def work():
                n = 0
                for d in sel:
                    for pg in d["pages"]:
                        pg["filter"], pg["bright"], pg["contrast"] = f, b, c
                        refresh_page_render(pg)
                        save_page_meta(pg)
                        n += 1
                return n

            run_bg(work, lambda n: (render_home_view(), toast(f"✨ Đã làm sáng {n} trang!")))

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("🎨 Chỉnh Sáng Hàng Loạt", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                dd,
                ft.Text("☀️ Độ sáng nền giấy:", size=12, weight=ft.FontWeight.BOLD), sb,
                ft.Text("✒️ Độ đậm nét chữ:", size=12, weight=ft.FontWeight.BOLD), sc,
            ], tight=True, spacing=4),
            actions=[ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                     Btn("Áp dụng ✓", bgcolor=CS_TEAL, color=WHITE, on_click=apply)])
        open_dlg(dlg)

    def filtered_and_sorted_docs():
        q = (app_data["search_query"] or "").strip().lower()
        q_ascii = strip_accents(q)
        fld = app_data["active_folder"]
        res = []
        for idx, d in enumerate(app_data["docs"]):
            df = d.get("folder", "Chung") or "Chung"
            if fld != "Tất cả" and df != fld:
                continue
            if q:
                title_l = d["title"].lower()
                if q not in title_l and q_ascii not in strip_accents(title_l):
                    continue
            res.append((idx, d))
        sm = app_data["sort_mode"]
        if sm == "name_asc":
            res.sort(key=lambda pair: natural_key(pair[1]["title"]))
        elif sm == "pages_desc":
            res.sort(key=lambda pair: len(pair[1]["pages"]), reverse=True)
        elif sm == "date_asc":
            res.sort(key=lambda pair: int(pair[1]["id"]) if str(pair[1]["id"]).isdigit() else 0)
        else:
            res.sort(key=lambda pair: int(pair[1]["id"]) if str(pair[1]["id"]).isdigit() else 0, reverse=True)
        return res

    def render_home_view():
        app_data["cam_running"] = False
        page.floating_action_button = None
        docs_list_col.controls.clear()
        sel_count = sum(1 for d in app_data["docs"] if d.get("selected"))
        trash_count = len(app_data["trash"])

        all_folders = ["Tất cả"] + sorted({d.get("folder", "Chung") or "Chung" for d in app_data["docs"]})
        if app_data["active_folder"] not in all_folders:
            app_data["active_folder"] = "Tất cả"

        folder_bar = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=6)
        for fd in all_folders:
            active = app_data["active_folder"] == fd
            folder_bar.controls.append(
                ft.Container(
                    padding=pad_sym(12, 5),
                    border_radius=16,
                    bgcolor=CS_TEAL if active else "#E0E6EA",
                    on_click=lambda e, f=fd: (app_data.update({"active_folder": f}), render_home_view()),
                    content=ft.Text(
                        f"📁 {fd}" if fd != "Tất cả" else f"📚 Tất cả ({len(app_data['docs'])})",
                        size=12, weight=ft.FontWeight.BOLD,
                        color=WHITE if active else "#37474F",
                    ),
                )
            )

        search_tf = ft.TextField(
            value=app_data["search_query"],
            hint_text="🔍 Tìm kiếm tài liệu...",
            height=38,
            text_size=13,
            content_padding=pad_sym(12, 4),
            border_radius=19,
            bgcolor="#F5F7F9",
            expand=True,
            on_change=lambda e: (app_data.update({"search_query": e.control.value}), refresh_doc_cards_only()),
        )

        sort_menu = ft.PopupMenuButton(
            icon=Icons.SORT,
            tooltip="Sắp xếp",
            items=[
                pm_item("🕒 Mới nhất trước", lambda _: (app_data.update({"sort_mode": "date_desc"}), render_home_view())),
                pm_item("🕰️ Cũ nhất trước", lambda _: (app_data.update({"sort_mode": "date_asc"}), render_home_view())),
                pm_item("🔤 Tên A → Z", lambda _: (app_data.update({"sort_mode": "name_asc"}), render_home_view())),
                pm_item("📄 Nhiều trang nhất", lambda _: (app_data.update({"sort_mode": "pages_desc"}), render_home_view())),
            ],
        )

        selection_bar = ft.Container(
            visible=(sel_count > 0),
            bgcolor="#E0F2F1",
            padding=pad_sym(10, 6),
            content=ft.Row([
                ft.Text(f"Đã chọn {sel_count}", size=12, weight=ft.FontWeight.BOLD, color=CS_TEAL),
                ft.Row([
                    ft.TextButton("Tất cả", on_click=lambda _: toggle_all_docs(True)),
                    ft.TextButton("Bỏ", on_click=lambda _: toggle_all_docs(False)),
                    ft.IconButton(Icons.AUTO_FIX_HIGH, icon_color=CS_TEAL, tooltip="Chỉnh sáng loạt", on_click=open_batch_dialog),
                    ft.IconButton(Icons.CALL_MERGE, icon_color="#3949AB", tooltip="Gộp tài liệu", on_click=merge_selected_docs),
                    ft.IconButton(Icons.PICTURE_AS_PDF, icon_color="#D84315", tooltip="Xuất PDF", on_click=export_selected_docs_pdf),
                    ft.IconButton(Icons.DELETE_OUTLINE, icon_color=Colors.RED_600, tooltip="Xóa", on_click=delete_selected_docs),
                ], spacing=0),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        )

        def refresh_doc_cards_only():
            docs_list_col.controls.clear()
            vis = filtered_and_sorted_docs()
            if not vis:
                docs_list_col.controls.append(ft.Container(height=320, alignment=ALIGN_CENTER, content=ft.Column([
                    ft.Icon(Icons.DOCUMENT_SCANNER_ROUNDED, size=68, color="#B0BEC5"),
                    ft.Text("Chưa có tài liệu nào", size=15, weight=ft.FontWeight.BOLD, color="#546E7A"),
                    ft.Text("Bấm nút '📸 Chụp Quét' hoặc '🖼️ Tải Ảnh' ở thanh dưới", size=12, color="#78909C"),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER)))
            else:
                for idx, doc in vis:
                    thumb = doc["pages"][0]["thumb_b64"] if doc["pages"] else ""
                    warn_cnt = sum(1 for pg in doc["pages"] if pg.get("is_blur") or pg.get("is_dark"))
                    warn_badge = f" • ⚠️ {warn_cnt} mờ/tối" if warn_cnt else ""
                    is_sel = bool(doc.get("selected", False))

                    def on_chk(e, i=idx):
                        app_data["docs"][i]["selected"] = e.control.value
                        save_doc(app_data["docs"][i])
                        render_home_view()

                    docs_list_col.controls.append(
                        ft.Container(
                            bgcolor="#E8F5E9" if is_sel else WHITE,
                            padding=pad_sym(8, 8),
                            border_radius=12,
                            border=border_all(1.5 if is_sel else 1, CS_TEAL if is_sel else "#E0E6EA"),
                            content=ft.Row([
                                ft.Checkbox(value=is_sel, active_color=CS_TEAL, on_change=on_chk),
                                ft.GestureDetector(
                                    on_tap=lambda e, i=idx: open_doc_studio(i),
                                    content=make_img(thumb, width=50, height=66, fit=FIT.COVER, border_radius=6),
                                ),
                                ft.Container(
                                    expand=True,
                                    on_click=lambda e, i=idx: open_doc_studio(i),
                                    content=ft.Column([
                                        ft.Text(doc["title"], weight=ft.FontWeight.BOLD, size=14, max_lines=1,
                                                overflow=ft.TextOverflow.ELLIPSIS),
                                        ft.Row([
                                            ft.Container(
                                                padding=pad_sym(6, 2), border_radius=6, bgcolor="#ECEFF1",
                                                content=ft.Text(f"📁 {doc.get('folder', 'Chung')}", size=10, color="#37474F"),
                                            ),
                                            ft.Text(f"📄 {len(doc['pages'])} trang{warn_badge}", size=11,
                                                    color=CS_ORANGE if warn_cnt else "#546E7A", weight=ft.FontWeight.BOLD),
                                        ], spacing=6),
                                        ft.Text(f"🕒 {doc['date']}", size=10, color="#78909C"),
                                    ], spacing=3),
                                ),
                                ft.PopupMenuButton(
                                    icon=Icons.MORE_VERT,
                                    icon_color="#546E7A",
                                    items=[
                                        pm_item("✏️ Đổi tên & Thư mục", lambda _, i=idx: rename_doc_dialog(i, render_home_view)),
                                        pm_item("📄 Xuất nhanh PDF", lambda _, i=idx: open_export_dialog(app_data["docs"][i]["title"], app_data["docs"][i]["pages"], "pdf")),
                                        pm_item("🖼️ Xuất ảnh JPG", lambda _, i=idx: open_export_dialog(app_data["docs"][i]["title"], app_data["docs"][i]["pages"], "jpg")),
                                        pm_item("🗑️ Xóa vào Thùng rác", lambda _, i=idx: (
                                            app_data["docs"][i].update({"selected": True}),
                                            delete_selected_docs()
                                        )),
                                    ],
                                ),
                            ], spacing=6),
                        )
                    )
            page.update()

        refresh_doc_cards_only()

        bottom_action_bar = ft.Container(
            bgcolor=WHITE,
            padding=pad_sym(12, 8),
            border=border_all(1, "#CFD8DC"),
            content=ft.Row([
                ft.Container(
                    expand=True,
                    height=46,
                    bgcolor=CS_ORANGE,
                    border_radius=23,
                    alignment=ALIGN_CENTER,
                    on_click=lambda _: open_camera_screen(new_doc=True, auto_crop=True, mode="doc"),
                    content=ft.Row([
                        ft.Icon(Icons.PHOTO_CAMERA, color=WHITE, size=20),
                        ft.Text("Chụp Quét", color=WHITE, weight=ft.FontWeight.BOLD, size=14),
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                ),
                ft.Container(
                    expand=True,
                    height=46,
                    bgcolor=CS_TEAL,
                    border_radius=23,
                    alignment=ALIGN_CENTER,
                    on_click=lambda _: show_import_sheet(True),
                    content=ft.Row([
                        ft.Icon(Icons.ADD_PHOTO_ALTERNATE, color=WHITE, size=20),
                        ft.Text("Tải Ảnh Lên", color=WHITE, weight=ft.FontWeight.BOLD, size=14),
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                ),
            ], spacing=10),
        )

        root_body.content = ft.Column([
            ft.Container(bgcolor=CS_TEAL, padding=pad_sym(14, 10), content=ft.Row([
                ft.Row([
                    ft.Icon(Icons.DOCUMENT_SCANNER, color=WHITE, size=22),
                    ft.Text("CS Scanner", color=WHITE, size=18, weight=ft.FontWeight.BOLD),
                ], spacing=8),
                ft.Row([
                    ft.IconButton(Icons.BACKUP_OUTLINED, icon_color=WHITE, tooltip="Sao lưu & Khôi phục (.ZIP)",
                                  on_click=open_backup_dialog),
                    ft.IconButton(Icons.RESTORE_FROM_TRASH, icon_color="#FFE082" if trash_count else WHITE,
                                  tooltip=f"Thùng rác ({trash_count})", on_click=open_trash_dialog),
                ], spacing=0),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)),

            ft.Container(bgcolor=WHITE, padding=pad_sym(10, 8), content=ft.Column([
                ft.Row([search_tf, sort_menu], spacing=2),
                folder_bar,
            ], spacing=8, tight=True)),

            selection_bar,

            ft.Container(padding=pad_sym(10, 4), expand=True, content=docs_list_col),

            bottom_action_bar,
        ], expand=True, spacing=0)
        page.update()

    # =================================================================
    # MÀN HÌNH 2: STUDIO ĐIỆN THOẠI (3 TẦNG CỐ ĐỊNH + BOTTOM DOCK 3 TAB)
    # =================================================================
    big_preview_img = make_img(fit=FIT.CONTAIN, expand=True)
    page_strip_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=6)
    page_badge_txt = ft.Text("", size=11, weight=ft.FontWeight.BOLD, color=WHITE)
    quality_alert_banner = ft.Container(visible=False, padding=pad_sym(10, 4), bgcolor="#FFF3E0")

    bright_slider = ft.Slider(min=0, max=85, divisions=17, value=38, label="{value}", active_color=CS_TEAL, expand=True)
    contrast_slider = ft.Slider(min=0, max=85, divisions=17, value=35, label="{value}", active_color=CS_TEAL, expand=True)
    sharp_slider = ft.Slider(min=0.0, max=2.5, divisions=10, value=1.0, label="{value}", active_color=CS_TEAL, expand=True)
    filter_chips_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=6)
    apply_all_switch = ft.Switch(label="Áp dụng cho mọi trang đang tích ☑️", value=True, active_color=CS_TEAL)

    studio_tab_body = ft.Container(padding=pad_sym(10, 8), bgcolor=WHITE)
    tab_btn_row = ft.Row(spacing=4)

    def target_pages():
        doc = cur_doc()
        if apply_all_switch.value:
            sel = [pg for pg in doc["pages"] if pg.get("selected")]
            if sel:
                return sel
        i = app_data["active_page_idx"]
        return [doc["pages"][i]] if 0 <= i < len(doc["pages"]) else []

    def apply_adjustment_to_targets(new_filter=None, rotate_delta=0):
        doc = cur_doc()
        if not doc["pages"]:
            return
        targets = target_pages()
        b, c, s = int(bright_slider.value), int(contrast_slider.value), float(sharp_slider.value)
        snapshot_doc(doc)

        def work():
            for pg in targets:
                if new_filter is not None:
                    pg["filter"] = new_filter
                if rotate_delta:
                    pg["rotation"] = (pg["rotation"] + rotate_delta) % 360
                pg["bright"], pg["contrast"], pg["sharp"] = b, c, s
                refresh_page_render(pg)
                save_page_meta(pg)

        run_bg(work, lambda _: refresh_studio_ui(), latest_wins=True)

    def batch_auto_crop_targets(use_ai):
        doc = cur_doc()
        targets = target_pages()
        snapshot_doc(doc)

        def work():
            for pg in targets:
                raw = read_image_utf8(p_raw(pg["id"]))
                if raw is None:
                    continue
                h, w = raw.shape[:2]
                pg["corners"] = auto_detect_corners(raw) if use_ai else full_corners(w, h)
                rebuild_warp(pg, raw)
                refresh_page_render(pg)
                save_page_meta(pg)

        run_bg(work, lambda _: (refresh_studio_ui(),
                                toast("🎯 Đã tự động cắt nền bàn!" if use_ai else "🖼️ Đã lấy lại toàn bộ ảnh gốc!")))

    bright_slider.on_change_end = lambda e: apply_adjustment_to_targets()
    contrast_slider.on_change_end = lambda e: apply_adjustment_to_targets()
    sharp_slider.on_change_end = lambda e: apply_adjustment_to_targets()

    def select_active_page(p_idx):
        doc = cur_doc()
        if not doc["pages"]:
            return
        p_idx = max(0, min(p_idx, len(doc["pages"]) - 1))
        app_data["active_page_idx"] = p_idx
        pg = doc["pages"][p_idx]
        bright_slider.value, contrast_slider.value, sharp_slider.value = pg["bright"], pg["contrast"], pg["sharp"]
        refresh_studio_ui()

    def toggle_page_checkbox(i, val):
        doc = cur_doc()
        doc["pages"][i]["selected"] = val
        save_page_meta(doc["pages"][i])
        refresh_studio_ui()

    def set_all_pages_checkbox(val):
        for pg in cur_doc()["pages"]:
            pg["selected"] = val
            save_page_meta(pg)
        refresh_studio_ui()

    def move_active_page(delta):
        doc = cur_doc()
        i = app_data["active_page_idx"]
        j = i + delta
        if not (0 <= j < len(doc["pages"])):
            return
        snapshot_doc(doc)
        doc["pages"][i], doc["pages"][j] = doc["pages"][j], doc["pages"][i]
        app_data["active_page_idx"] = j
        save_doc(doc)
        refresh_studio_ui()

    def sort_pages(mode):
        doc = cur_doc()
        if len(doc["pages"]) < 2:
            return
        snapshot_doc(doc)
        cur_id = doc["pages"][app_data["active_page_idx"]]["id"]
        if mode == "name":
            doc["pages"].sort(key=lambda pg: natural_key(pg.get("name", "")))
        else:
            doc["pages"].reverse()
        app_data["active_page_idx"] = [pg["id"] for pg in doc["pages"]].index(cur_id)
        save_doc(doc)
        refresh_studio_ui()
        toast("🔤 Đã xếp theo tên gốc" if mode == "name" else "🔃 Đã đảo thứ tự trang")

    def move_to_dialog(e=None):
        doc = cur_doc()
        n = len(doc["pages"])
        tf = ft.TextField(label=f"Chuyển tới vị trí (1 - {n})", keyboard_type=ft.KeyboardType.NUMBER, autofocus=True)

        def go(ev):
            try:
                j = int((tf.value or "").strip())
            except ValueError:
                j = 0
            if not 1 <= j <= n:
                tf.error_text = f"Nhập từ 1 đến {n}"
                page.update()
                return
            snapshot_doc(doc)
            pg = doc["pages"].pop(app_data["active_page_idx"])
            doc["pages"].insert(j - 1, pg)
            app_data["active_page_idx"] = j - 1
            save_doc(doc)
            close_dlg(dlg)
            refresh_studio_ui()

        tf.on_submit = go
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("↔ Đổi vị trí trang", size=16, weight=ft.FontWeight.BOLD), content=tf,
            actions=[ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                     Btn("Chuyển", bgcolor=CS_TEAL, color=WHITE, on_click=go)])
        open_dlg(dlg)

    def undo_last(e=None):
        doc = cur_doc()
        if not doc["undo"]:
            toast("Không còn bước nào để hoàn tác", Colors.ORANGE_800)
            return
        snap = doc["undo"].pop()
        run_bg(lambda: restore_snapshot(doc, snap),
               lambda _: (select_active_page(app_data["active_page_idx"]), toast("↩️ Đã hoàn tác")))

    def delete_selected_pages(e=None):
        doc = cur_doc()
        sel = [pg for pg in doc["pages"] if pg.get("selected")]
        removed = sel if sel else ([doc["pages"][app_data["active_page_idx"]]] if doc["pages"] else [])
        if not removed:
            return

        def go():
            rm_ids = {pg["id"] for pg in removed}
            move_pages_to_trash(doc, removed)
            app_data["trash"] = purge_and_load_trash()
            doc["pages"] = [pg for pg in doc["pages"] if pg["id"] not in rm_ids]
            doc["undo"].clear()
            if not doc["pages"]:
                delete_doc_json(doc)
                app_data["docs"].pop(app_data["current_doc_idx"])
                render_home_view()
                toast(f"🗑️ Đã xóa {len(removed)} trang vào Thùng rác!")
                return
            save_doc(doc)
            select_active_page(min(app_data["active_page_idx"], len(doc["pages"]) - 1))
            toast(f"🗑️ Đã chuyển {len(removed)} trang vào Thùng rác!")

        confirm_dlg("Xóa trang?", f"Chuyển {len(removed)} trang vào Thùng rác (giữ 7 ngày)?", go, "Xóa")

    # ---------- Ghép 2 / 4 / 6 trang vào 1 trang A4 ----------
    def open_multi_grid_dialog(e=None):
        doc = cur_doc()
        sel = [pg for pg in doc["pages"] if pg.get("selected")]
        if len(sel) < 2:
            toast("🪪 Hãy tích chọn từ 2 đến 6 trang ở dải bên dưới để ghép!", Colors.ORANGE_800)
            return
        default_layout = "2" if len(sel) == 2 else ("4" if len(sel) <= 4 else "6")
        dd_layout = ft.Dropdown(label="Kiểu ghép trên 1 mặt A4", value=default_layout, options=[
            DDOpt(key="2", text="2 mặt / A4 (Ghép CCCD, Bằng lái)"),
            DDOpt(key="4", text="4 trang / A4 (Lưới 2x2)"),
            DDOpt(key="6", text="6 trang / A4 (Lưới 3x2)"),
        ])

        def do_merge(_):
            layout = int(dd_layout.value or "2")
            chosen = sel[:layout]
            close_dlg(dlg)

            def work():
                imgs = [render_full(p, 1600) for p in chosen]
                canvas = compose_multi_grid_a4(imgs, layout=layout, dpi=200)
                return create_page_from_raw(canvas, auto_crop=False, filter="raw", sharp=0.0,
                                            name=f"Ghep_{layout}_trang.jpg")

            def done(newpg):
                ids = [p["id"] for p in doc["pages"]]
                pos = max(ids.index(p["id"]) for p in chosen) + 1
                for p in chosen:
                    p["selected"] = False
                    save_page_meta(p)
                doc["pages"].insert(pos, newpg)
                doc["undo"].clear()
                save_doc(doc)
                app_data["active_page_idx"] = pos
                select_active_page(pos)
                toast(f"🪪 Đã ghép {len(chosen)} trang vào 1 mặt A4!")

            run_bg(work, done)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"🪪 Ghép vào 1 trang A4 ({len(sel)} trang)", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column([dd_layout], tight=True, spacing=8),
            actions=[
                ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                Btn("Ghép ngay ✓", bgcolor=CS_TEAL, color=WHITE, on_click=do_merge),
            ],
        )
        open_dlg(dlg)

    # ---------- Đóng dấu chữ mờ (Watermark) ----------
    def open_watermark_dialog(e=None):
        doc = cur_doc()
        cur = doc["pages"][app_data["active_page_idx"]]
        default_wm = cur.get("watermark", "") or f"Bản sao chỉ dùng nộp hồ sơ ngày {time.strftime('%d/%m/%Y')}"
        tf_wm = ft.TextField(value=default_wm, label="Nội dung đóng dấu mờ", autofocus=True)
        sl_op = ft.Slider(min=0.08, max=0.55, divisions=9, value=float(cur.get("wm_opacity", 0.22)),
                          label="Độ đậm: {value}")
        sw_all = ft.Switch(label="Áp dụng mọi trang đang tích ☑️", value=True, active_color=CS_TEAL)

        def apply_wm(clear=False):
            txt = "" if clear else (tf_wm.value or "").strip()
            op = float(sl_op.value)
            targets = [pg for pg in doc["pages"] if pg.get("selected")] if sw_all.value else [cur]
            if not targets:
                targets = [cur]
            snapshot_doc(doc)
            close_dlg(dlg)

            def work():
                for pg in targets:
                    pg["watermark"] = txt
                    pg["wm_opacity"] = op
                    refresh_page_render(pg)
                    save_page_meta(pg)

            run_bg(work, lambda _: (refresh_studio_ui(),
                                    toast("🚫 Đã gỡ dấu mờ!" if clear else "🔖 Đã đóng dấu chữ mờ!")))

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("🔖 Đóng dấu chữ mờ (Watermark)", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column([tf_wm, ft.Text("Độ đậm chữ mờ:", size=12), sl_op, sw_all], tight=True, spacing=4),
            actions=[
                ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                OutBtn("Gỡ dấu", on_click=lambda _: apply_wm(clear=True)),
                Btn("Đóng dấu ✓", bgcolor=CS_TEAL, color=WHITE, on_click=lambda _: apply_wm(clear=False)),
            ],
        )
        open_dlg(dlg)

    def build_studio_tab_content():
        t_mode = app_data.get("studio_tab", "color")
        tab_btn_row.controls.clear()
        tabs_meta = [
            ("color", Icons.PALETTE_OUTLINED, "Màu & Sáng"),
            ("crop", Icons.CROP_ROTATE, "Cắt & Xoay"),
            ("secure", Icons.VERIFIED_USER_OUTLINED, "Bảo mật & Ghép"),
        ]
        for code, ic, lb in tabs_meta:
            active = (t_mode == code)
            tab_btn_row.controls.append(
                ft.Container(
                    expand=True,
                    padding=pad_sym(6, 7),
                    border_radius=8,
                    bgcolor=CS_TEAL if active else "#ECEFF1",
                    alignment=ALIGN_CENTER,
                    on_click=lambda e, c=code: (app_data.update({"studio_tab": c}), build_studio_tab_content(), page.update()),
                    content=ft.Row([
                        ft.Icon(ic, size=16, color=WHITE if active else "#455A64"),
                        ft.Text(lb, size=12, weight=ft.FontWeight.BOLD, color=WHITE if active else "#455A64"),
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=4),
                )
            )

        if t_mode == "color":
            studio_tab_body.content = ft.Column([
                filter_chips_row,
                ft.Row([
                    ft.Text("☀️ Sáng nền", size=11, weight=ft.FontWeight.BOLD, width=78),
                    bright_slider,
                ], spacing=4),
                ft.Row([
                    ft.Text("✒️ Đậm chữ", size=11, weight=ft.FontWeight.BOLD, width=78),
                    contrast_slider,
                ], spacing=4),
                ft.Row([
                    ft.Text("✨ Sắc nét", size=11, weight=ft.FontWeight.BOLD, width=78),
                    sharp_slider,
                ], spacing=4),
                apply_all_switch,
            ], spacing=2, tight=True)

        elif t_mode == "crop":
            studio_tab_body.content = ft.Column([
                ft.Row([
                    mobile_action_tile(Icons.CROP, "Kéo 4 Góc", lambda _: open_crop_screen(app_data["active_page_idx"]),
                                       bg="#FFF3E0", icon_col=CS_ORANGE),
                    mobile_action_tile(Icons.CROP_FREE, "AI Tự Cắt", lambda _: batch_auto_crop_targets(True)),
                    mobile_action_tile(Icons.ROTATE_RIGHT, "Xoay 90°", lambda _: apply_adjustment_to_targets(rotate_delta=90)),
                    mobile_action_tile(Icons.FULLSCREEN, "Khung Gốc", lambda _: batch_auto_crop_targets(False)),
                ], spacing=6),
                ft.Row([
                    mobile_action_tile(Icons.ARROW_BACK, "Dời Trái", lambda _: move_active_page(-1), icon_col="#3949AB"),
                    mobile_action_tile(Icons.ARROW_FORWARD, "Dời Phải", lambda _: move_active_page(1), icon_col="#3949AB"),
                    mobile_action_tile(Icons.SWAP_VERT, "Đổi Vị Trí", move_to_dialog, icon_col="#3949AB"),
                    mobile_action_tile(Icons.DELETE_OUTLINE, "Xóa Trang", delete_selected_pages,
                                       bg="#FFEBEE", icon_col=Colors.RED_600),
                ], spacing=6),
            ], spacing=6, tight=True)

        else:  # secure
            studio_tab_body.content = ft.Column([
                ft.Row([
                    mobile_action_tile(Icons.VISIBILITY_OFF, "Che CCCD/TK",
                                       lambda _: open_redact_screen(app_data["active_page_idx"]),
                                       bg="#ECEFF1", icon_col="#263238"),
                    mobile_action_tile(Icons.DRAW, "Chèn Chữ Ký",
                                       lambda _: open_signature_screen(app_data["active_page_idx"]),
                                       bg="#E8EAF6", icon_col="#283593"),
                ], spacing=8),
                ft.Row([
                    mobile_action_tile(Icons.BRANDING_WATERMARK, "Đóng Dấu Mờ",
                                       open_watermark_dialog, bg="#FCE4EC", icon_col="#AD1457"),
                    mobile_action_tile(Icons.GRID_VIEW_ROUNDED, "Ghép 2/4/6 A4",
                                       open_multi_grid_dialog, bg="#E0F2F1", icon_col=CS_TEAL),
                ], spacing=8),
            ], spacing=6, tight=True)

    def refresh_studio_ui():
        doc = cur_doc()
        if not doc["pages"]:
            render_home_view()
            return
        p_idx = max(0, min(app_data["active_page_idx"], len(doc["pages"]) - 1))
        app_data["active_page_idx"] = p_idx
        cur = doc["pages"][p_idx]
        set_img(big_preview_img, cur["view_b64"])
        try:
            big_preview_img.update()
        except Exception:
            pass
        sel_cnt = sum(1 for pg in doc["pages"] if pg.get("selected"))
        page_badge_txt.value = f"Trang {p_idx + 1}/{len(doc['pages'])} • Chọn: {sel_cnt}"

        warns = []
        if cur.get("is_blur"):
            warns.append("Ảnh hơi mờ")
        if cur.get("is_dark"):
            warns.append("Ảnh thiếu sáng")
        if warns:
            quality_alert_banner.visible = True
            quality_alert_banner.content = ft.Row([
                ft.Icon(Icons.WARNING_AMBER_ROUNDED, color=CS_ORANGE, size=16),
                ft.Text(" & ".join(warns) + " — Bấm '🔍 Xem rõ' để kiểm tra!", size=11, color=CS_ORANGE,
                        weight=ft.FontWeight.BOLD, expand=True),
            ], spacing=4)
        else:
            quality_alert_banner.visible = False

        filter_chips_row.controls.clear()
        for code, label in FILTER_OPTIONS:
            on = cur["filter"] == code
            filter_chips_row.controls.append(
                ft.Container(
                    padding=pad_sym(10, 6),
                    border_radius=14,
                    bgcolor=CS_TEAL if on else "#E0E6EA",
                    on_click=lambda e, c=code: apply_adjustment_to_targets(new_filter=c),
                    content=ft.Text(label, size=11, weight=ft.FontWeight.BOLD, color=WHITE if on else "#263238"),
                )
            )

        page_strip_row.controls.clear()
        for i, pg in enumerate(doc["pages"]):
            viewing = i == p_idx
            bad = pg.get("is_blur") or pg.get("is_dark")
            badge_txt = f"{i + 1}⚠️" if bad else f"{i + 1}"
            page_strip_row.controls.append(ft.Container(
                width=68, padding=3, border_radius=8,
                bgcolor="#FFF3E0" if bad and not viewing else ("#E0F2F1" if viewing else "#F5F7F9"),
                border=border_all(2.5 if viewing else 1, CS_TEAL if viewing else ("#FB8C00" if bad else "#CFD8DC")),
                content=ft.Column([
                    ft.GestureDetector(
                        on_tap=lambda e, idx=i: select_active_page(idx),
                        content=make_img(pg["thumb_b64"], width=58, height=64, fit=FIT.COVER, border_radius=4),
                    ),
                    ft.Row([
                        ft.Checkbox(value=pg.get("selected", False), active_color=CS_TEAL,
                                    on_change=lambda e, idx=i: toggle_page_checkbox(idx, e.control.value)),
                        ft.Text(badge_txt, size=10, weight=ft.FontWeight.BOLD,
                                color=CS_ORANGE if bad else "#263238"),
                    ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
                ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ))
        build_studio_tab_content()
        page.update()

    def open_doc_studio(doc_idx, keep_page=False):
        app_data["cam_running"] = False
        app_data["current_doc_idx"] = doc_idx
        page.floating_action_button = None
        doc = app_data["docs"][doc_idx]
        if doc["pages"]:
            if not keep_page:
                app_data["active_page_idx"] = 0
            app_data["active_page_idx"] = min(app_data["active_page_idx"], len(doc["pages"]) - 1)
            cur = doc["pages"][app_data["active_page_idx"]]
            bright_slider.value, contrast_slider.value, sharp_slider.value = cur["bright"], cur["contrast"], cur["sharp"]
        refresh_studio_ui()

        root_body.content = ft.Column(expand=True, spacing=0, controls=[
            ft.Container(bgcolor=CS_TEAL, padding=pad_sym(6, 6), content=ft.Row([
                ft.IconButton(Icons.ARROW_BACK, icon_color=WHITE, on_click=lambda _: render_home_view()),
                ft.Container(
                    expand=True,
                    on_click=lambda _: rename_doc_dialog(
                        app_data["current_doc_idx"],
                        lambda: open_doc_studio(app_data["current_doc_idx"], keep_page=True),
                    ),
                    content=ft.Column([
                        ft.Text(doc["title"], color=WHITE, size=14, weight=ft.FontWeight.BOLD,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(f"📁 {doc.get('folder', 'Chung')} (Chạm để đổi tên)", color="#A7FFEB", size=10),
                    ], spacing=0),
                ),
                ft.Container(
                    bgcolor="#D84315", padding=pad_sym(10, 6), border_radius=16,
                    on_click=export_current_doc_pdf,
                    content=ft.Row([
                        ft.Icon(Icons.PICTURE_AS_PDF, color=WHITE, size=16),
                        ft.Text("Xuất PDF", color=WHITE, size=12, weight=ft.FontWeight.BOLD),
                    ], spacing=4),
                ),
                ft.PopupMenuButton(icon=Icons.MORE_VERT, icon_color=WHITE, items=[
                    pm_item("📄 Xuất PDF (Nén theo MB)...", export_current_doc_pdf),
                    pm_item("🖼️ Xuất ảnh JPG...", export_current_doc_jpgs),
                    pm_item("🔤 Sắp xếp trang theo tên gốc", lambda _: sort_pages("name")),
                    pm_item("🔃 Đảo ngược thứ tự trang", lambda _: sort_pages("reverse")),
                ]),
            ], spacing=4)),

            quality_alert_banner,

            ft.Container(
                expand=True,
                bgcolor="#1E272C",
                padding=6,
                content=ft.Stack([
                    ft.GestureDetector(
                        on_tap=lambda _: open_preview(app_data["active_page_idx"]),
                        content=ft.Container(expand=True, alignment=ALIGN_CENTER, content=big_preview_img),
                    ),
                    ft.Container(
                        left=8, top=6,
                        bgcolor="#AA000000", padding=pad_sym(10, 4), border_radius=12,
                        content=page_badge_txt,
                    ),
                    ft.Row([
                        ft.Container(
                            bgcolor="#CC263238", padding=pad_sym(10, 5), border_radius=14,
                            on_click=undo_last,
                            content=ft.Row([
                                ft.Icon(Icons.UNDO, color=WHITE, size=15),
                                ft.Text("Hoàn tác", color=WHITE, size=11, weight=ft.FontWeight.BOLD),
                            ], spacing=4),
                        ),
                        ft.Container(
                            bgcolor="#CC00897B", padding=pad_sym(10, 5), border_radius=14,
                            on_click=lambda _: open_preview(app_data["active_page_idx"]),
                            content=ft.Row([
                                ft.Icon(Icons.ZOOM_IN, color=WHITE, size=15),
                                ft.Text("Xem rõ", color=WHITE, size=11, weight=ft.FontWeight.BOLD),
                            ], spacing=4),
                        ),
                    ], right=8, bottom=6, spacing=6),
                ], expand=True),
            ),

            ft.Container(
                bgcolor=WHITE,
                padding=pad_sym(8, 4),
                border=border_all(1, "#E0E6EA"),
                content=ft.Column([
                    ft.Row([
                        ft.Row([
                            ft.TextButton("☑️ Tất cả", on_click=lambda _: set_all_pages_checkbox(True)),
                            ft.TextButton("⬜ Bỏ chọn", on_click=lambda _: set_all_pages_checkbox(False)),
                        ], spacing=0),
                        ft.Row([
                            ft.Container(
                                bgcolor=CS_ORANGE, padding=pad_sym(10, 5), border_radius=14,
                                on_click=lambda _: open_camera_screen(new_doc=False, auto_crop=True, mode="doc"),
                                content=ft.Text("📸 +Chụp", color=WHITE, size=11, weight=ft.FontWeight.BOLD),
                            ),
                            ft.Container(
                                bgcolor=CS_TEAL, padding=pad_sym(10, 5), border_radius=14,
                                on_click=lambda _: show_import_sheet(False),
                                content=ft.Text("🖼️ +Ảnh", color=WHITE, size=11, weight=ft.FontWeight.BOLD),
                            ),
                        ], spacing=6),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    page_strip_row,
                ], spacing=2, tight=True),
            ),

            ft.Container(
                bgcolor=WHITE,
                padding=pad_sym(8, 4),
                content=ft.Column([
                    tab_btn_row,
                    studio_tab_body,
                ], spacing=4, tight=True),
            ),
        ])
        page.update()

    # =================================================================
    # MÀN HÌNH 3: KÉO 4 GÓC THỦ CÔNG
    # =================================================================
    MAX_CROP_W, MAX_CROP_H = 350, 450
    crop_bg_image = make_img(width=MAX_CROP_W, height=MAX_CROP_H, fit=FIT.FILL)
    crop_ui = {"w": MAX_CROP_W, "h": MAX_CROP_H, "pts": [[20, 20], [330, 20], [330, 430], [20, 430]], "sx": 1.0, "sy": 1.0}
    corner_handles = []

    def update_crop_canvas():
        disp = app_data["crop_disp"]
        if disp is None:
            return
        disp = disp.copy()
        pts = np.array(crop_ui["pts"], dtype=np.int32)
        overlay = disp.copy()
        cv2.fillPoly(overlay, [pts], (180, 210, 0))
        cv2.addWeighted(overlay, 0.20, disp, 0.80, 0, disp)
        cv2.polylines(disp, [pts], True, (212, 188, 0), 3, cv2.LINE_AA)
        set_img(crop_bg_image, img_to_b64(disp, 82))

    def drag_corner_point(e, idx):
        dx, dy = drag_delta(e)
        cw, ch = crop_ui["w"], crop_ui["h"]
        nx = max(0, min(cw, crop_ui["pts"][idx][0] + dx))
        ny = max(0, min(ch, crop_ui["pts"][idx][1] + dy))
        crop_ui["pts"][idx] = [nx, ny]
        corner_handles[idx].left = nx - 20
        corner_handles[idx].top = ny - 20
        update_crop_canvas()
        page.update()

    for i in range(4):
        corner_handles.append(ft.GestureDetector(
            left=0, top=0, on_pan_update=lambda e, ci=i: drag_corner_point(e, ci),
            content=ft.Container(width=40, height=40, border_radius=20, bgcolor="#8800BFA5",
                                 border=border_all(3, WHITE), alignment=ALIGN_CENTER,
                                 content=ft.Container(width=10, height=10, border_radius=5, bgcolor="#FF1744"))))

    def sync_corners_to_handles(real_corners):
        h, w = app_data["crop_raw"].shape[:2]
        cw, ch = crop_ui["w"], crop_ui["h"]
        crop_ui["sx"], crop_ui["sy"] = w / float(cw), h / float(ch)
        for i in range(4):
            cx, cy = float(real_corners[i][0]) / crop_ui["sx"], float(real_corners[i][1]) / crop_ui["sy"]
            crop_ui["pts"][i] = [cx, cy]
            corner_handles[i].left, corner_handles[i].top = cx - 20, cy - 20
        update_crop_canvas()

    def apply_crop_to_page(e):
        doc = cur_doc()
        pg = doc["pages"][app_data["crop_target_idx"]]
        snapshot_doc(doc)
        pg["corners"] = np.array([[p[0] * crop_ui["sx"], p[1] * crop_ui["sy"]] for p in crop_ui["pts"]],
                                 dtype="float32")
        raw = app_data["crop_raw"]

        def work():
            rebuild_warp(pg, raw)
            refresh_page_render(pg)
            save_page_meta(pg)

        run_bg(work, lambda _: (open_doc_studio(app_data["current_doc_idx"], keep_page=True),
                                toast("📐 Đã cắt phẳng trang giấy!")))

    def open_crop_screen(p_idx):
        doc = cur_doc()
        pg = doc["pages"][p_idx]
        app_data["crop_target_idx"] = p_idx
        raw = read_image_utf8(p_raw(pg["id"]))
        if raw is None:
            raw = get_warped(pg)
        app_data["crop_raw"] = raw
        rh, rw = raw.shape[:2]
        scale = min(MAX_CROP_W / float(rw), MAX_CROP_H / float(rh))
        cw, ch = max(120, int(rw * scale)), max(120, int(rh * scale))
        crop_ui["w"], crop_ui["h"] = cw, ch
        crop_bg_image.width, crop_bg_image.height = cw, ch
        app_data["crop_disp"] = cv2.resize(raw, (cw, ch), interpolation=cv2.INTER_AREA)
        sync_corners_to_handles(pg["corners"])

        def full(_):
            h, w = app_data["crop_raw"].shape[:2]
            sync_corners_to_handles(full_corners(w, h))
            page.update()

        def ai(_):
            sync_corners_to_handles(auto_detect_corners(app_data["crop_raw"]))
            page.update()

        root_body.content = ft.Container(bgcolor=CS_DARK, expand=True, content=ft.Column([
            ft.Container(padding=pad_sym(8, 8), bgcolor="#11171A", content=ft.Row([
                ft.IconButton(Icons.ARROW_BACK, icon_color=WHITE,
                              on_click=lambda _: open_doc_studio(app_data["current_doc_idx"], keep_page=True)),
                ft.Text(f"Chỉnh 4 Góc - Trang {p_idx + 1}", color=WHITE, weight=ft.FontWeight.BOLD, expand=True),
                Btn("Cắt Phẳng ✓", bgcolor=CS_TEAL, color=WHITE, on_click=apply_crop_to_page),
            ])),
            ft.Text("Kéo 4 vòng tròn vào 4 góc tờ giấy", color="#B0BEC5", size=12),
            ft.Container(expand=True, alignment=ALIGN_CENTER,
                         content=ft.Stack(width=cw, height=ch, controls=[crop_bg_image] + corner_handles)),
            ft.Container(bgcolor="#11171A", padding=10, content=ft.Row([
                OutBtn("🖼️ Lấy hết khung", on_click=full),
                Btn("🎯 AI Tự bắt góc", bgcolor=CS_TEAL, color=WHITE, on_click=ai),
            ], alignment=ft.MainAxisAlignment.SPACE_EVENLY)),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True))
        page.update()

    # =================================================================
    # MÀN HÌNH 4: CHE THÔNG TIN NHẠY CẢM
    # =================================================================
    def open_redact_screen(p_idx):
        doc = cur_doc()
        pg = doc["pages"][p_idx]
        base_img = process_page_image(
            get_prev(pg), pg["filter"], pg["bright"], pg["contrast"], pg["sharp"], pg["rotation"],
            redactions=None, signatures=None, watermark=""
        )
        bh, bw = base_img.shape[:2]
        scale = min(MAX_CROP_W / float(bw), MAX_CROP_H / float(bh))
        cw, ch = max(120, int(bw * scale)), max(120, int(bh * scale))
        disp_base = cv2.resize(base_img, (cw, ch), interpolation=cv2.INTER_AREA)

        state = {
            "boxes": [
                {
                    "x1": float(r.get("x1", 0)),
                    "y1": float(r.get("y1", 0)),
                    "x2": float(r.get("x2", 0)),
                    "y2": float(r.get("y2", 0)),
                    "mode": str(r.get("mode", "black")),
                }
                for r in pg.get("redactions", [])
            ],
            "mode": "black",
            "sx": 0.0,
            "sy": 0.0,
            "cx": 0.0,
            "cy": 0.0,
            "dragging": False,
            "tick": 0,
        }

        red_img = make_img(width=cw, height=ch, fit=FIT.FILL)
        count_txt = ft.Text("", color="#A7FFEB", size=11, weight=ft.FontWeight.BOLD)
        undo_btn = OutBtn("↩️ Bỏ ô (0)")
        clear_btn = OutBtn("🗑️ Xóa hết")
        mode_row = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=6)

        def build_mode_pills():
            mode_row.controls.clear()
            for m_code, m_label in [("black", "⬛ Ô đen"), ("pixel", "🟧 Làm mờ"), ("white", "⬜ Xóa trắng")]:
                on = (state["mode"] == m_code)
                mode_row.controls.append(
                    ft.Container(
                        padding=pad_sym(12, 6),
                        border_radius=14,
                        bgcolor=CS_TEAL if on else "#263238",
                        on_click=lambda e, mc=m_code: (state.update({"mode": mc}), build_mode_pills(), page.update()),
                        content=ft.Text(m_label, size=11, weight=ft.FontWeight.BOLD, color=WHITE),
                    )
                )

        def redraw():
            canvas = disp_base.copy()
            if state["boxes"]:
                canvas = apply_redactions(canvas, state["boxes"])
                for b in state["boxes"]:
                    bx1, by1 = int(b["x1"] * cw), int(b["y1"] * ch)
                    bx2, by2 = int(b["x2"] * cw), int(b["y2"] * ch)
                    cv2.rectangle(canvas, (bx1, by1), (bx2, by2), (0, 191, 165), 1)

            if state["dragging"]:
                x1, y1 = int(min(state["sx"], state["cx"])), int(min(state["sy"], state["cy"]))
                x2, y2 = int(max(state["sx"], state["cx"])), int(max(state["sy"], state["cy"]))
                cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 230, 118), 2)

            state["tick"] += 1
            q_val = 85 + (state["tick"] % 2)
            set_img(red_img, img_to_b64(canvas, q_val))

            n_boxes = len(state["boxes"])
            count_txt.value = f"Đã che: {n_boxes} vùng (Kéo ngón tay để vẽ • Chạm vào ô để xóa)"
            set_btn_text(undo_btn, f"↩️ Bỏ ô ({n_boxes})")
            undo_btn.disabled = (n_boxes == 0)
            clear_btn.disabled = (n_boxes == 0)

            try:
                red_img.update()
            except Exception:
                pass
            page.update()

        def on_tap_box_to_delete(e):
            lx, ly = drag_pos(e)
            if lx is None or ly is None or not state["boxes"]:
                return
            nx, ny = lx / float(cw), ly / float(ch)
            for i in range(len(state["boxes"]) - 1, -1, -1):
                b = state["boxes"][i]
                if b["x1"] <= nx <= b["x2"] and b["y1"] <= ny <= b["y2"]:
                    state["boxes"].pop(i)
                    redraw()
                    toast("🗑️ Đã xóa ô vừa chạm!")
                    return

        def on_pan_start(e):
            lx, ly = drag_pos(e)
            if lx is None or ly is None:
                return
            state["sx"] = state["cx"] = max(0.0, min(float(cw), lx))
            state["sy"] = state["cy"] = max(0.0, min(float(ch), ly))
            state["dragging"] = True
            redraw()

        def on_pan_update(e):
            if not state["dragging"]:
                return
            lx, ly = drag_pos(e)
            if lx is not None and ly is not None:
                state["cx"] = max(0.0, min(float(cw), lx))
                state["cy"] = max(0.0, min(float(ch), ly))
            else:
                dx, dy = drag_delta(e)
                state["cx"] = max(0.0, min(float(cw), state["cx"] + dx))
                state["cy"] = max(0.0, min(float(ch), state["cy"] + dy))
            redraw()

        def on_pan_end(e):
            if not state["dragging"]:
                return
            state["dragging"] = False
            x1, x2 = sorted([state["sx"] / float(cw), state["cx"] / float(cw)])
            y1, y2 = sorted([state["sy"] / float(ch), state["cy"] / float(ch)])
            if (x2 - x1) * cw >= 8 and (y2 - y1) * ch >= 8:
                state["boxes"].append({
                    "x1": round(x1, 4),
                    "y1": round(y1, 4),
                    "x2": round(x2, 4),
                    "y2": round(y2, 4),
                    "mode": state["mode"],
                })
            redraw()

        def undo_last_box(e):
            if state["boxes"]:
                state["boxes"].pop()
                redraw()

        def clear_all_boxes(e):
            if state["boxes"]:
                state["boxes"].clear()
                redraw()
                toast("🗑️ Đã xóa hết các ô che!")

        def save_redactions(e):
            snapshot_doc(doc)
            pg["redactions"] = [dict(b) for b in state["boxes"]]

            def work():
                refresh_page_render(pg)
                save_page_meta(pg)

            def done(_):
                open_doc_studio(app_data["current_doc_idx"], keep_page=True)
                toast(f"⬛ Đã lưu {len(pg['redactions'])} vùng che thông tin!")

            run_bg(work, done)

        undo_btn.on_click = undo_last_box
        clear_btn.on_click = clear_all_boxes
        build_mode_pills()

        root_body.content = ft.Container(bgcolor=CS_DARK, expand=True, content=ft.Column([
            ft.Container(padding=pad_sym(8, 8), bgcolor="#11171A", content=ft.Row([
                ft.IconButton(Icons.ARROW_BACK, icon_color=WHITE,
                              on_click=lambda _: open_doc_studio(app_data["current_doc_idx"], keep_page=True)),
                ft.Text(f"Che Thông Tin - Trang {p_idx + 1}", color=WHITE, weight=ft.FontWeight.BOLD, expand=True),
                Btn("Lưu ✓", bgcolor=CS_TEAL, color=WHITE, on_click=save_redactions),
            ])),
            count_txt,
            ft.Container(
                expand=True, alignment=ALIGN_CENTER,
                content=ft.Stack(
                    width=cw, height=ch,
                    controls=[
                        red_img,
                        ft.GestureDetector(
                            left=0, top=0, width=cw, height=ch,
                            on_tap_down=on_tap_box_to_delete,
                            on_pan_start=on_pan_start,
                            on_pan_update=on_pan_update,
                            on_pan_end=on_pan_end,
                            content=ft.Container(width=cw, height=ch, bgcolor="#00000000"),
                        ),
                    ],
                ),
            ),
            ft.Container(bgcolor="#11171A", padding=10, content=ft.Column([
                mode_row,
                ft.Row([undo_btn, clear_btn], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
            ], spacing=8, tight=True)),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True))
        redraw()

    # =================================================================
    # MÀN HÌNH 5: TÁCH NỀN & CHÈN CHỮ KÝ
    # =================================================================
    def list_saved_signatures():
        if not os.path.isdir(SIG_DIR):
            return []
        return sorted([f for f in os.listdir(SIG_DIR) if f.endswith(".png")])

    def open_signature_screen(p_idx):
        doc = cur_doc()
        pg = doc["pages"][p_idx]
        base_img = process_page_image(get_prev(pg), pg["filter"], pg["bright"], pg["contrast"], pg["sharp"],
                                      pg["rotation"], redactions=pg.get("redactions"))
        bh, bw = base_img.shape[:2]
        scale = min(MAX_CROP_W / float(bw), MAX_CROP_H / float(bh))
        cw, ch = max(120, int(bw * scale)), max(120, int(bh * scale))
        disp_base = cv2.resize(base_img, (cw, ch), interpolation=cv2.INTER_AREA)

        sigs = list_saved_signatures()
        existing = [dict(s) for s in pg.get("signatures", [])]
        active_sig = dict(existing[-1]) if existing else {
            "file": sigs[0] if sigs else "",
            "x": 0.72,
            "y": 0.82,
            "w": 0.30,
            "opacity": 0.95,
        }

        sig_preview = make_img(width=cw, height=ch, fit=FIT.FILL)
        size_slider = ft.Slider(min=0.12, max=0.65, divisions=15, value=float(active_sig.get("w", 0.30)),
                                label="Cỡ: {value}", active_color=CS_ACCENT, expand=True)
        sig_handle = ft.GestureDetector(
            left=int(active_sig["x"] * cw) - 22,
            top=int(active_sig["y"] * ch) - 22,
            content=ft.Container(
                width=44, height=44, border_radius=22,
                bgcolor="#6600BFA5", border=border_all(2, WHITE),
                alignment=ALIGN_CENTER,
                content=ft.Icon(Icons.OPEN_WITH, color=WHITE, size=20),
            ),
        )

        def current_sig_list():
            if not active_sig.get("file"):
                return existing[:-1] if existing else []
            if existing:
                return existing[:-1] + [active_sig]
            return [active_sig]

        def redraw():
            canvas = apply_signatures(disp_base, current_sig_list())
            sig_handle.visible = bool(active_sig.get("file"))
            sig_handle.left = max(0, min(cw - 44, int(active_sig["x"] * cw) - 22))
            sig_handle.top = max(0, min(ch - 44, int(active_sig["y"] * ch) - 22))
            set_img(sig_preview, img_to_b64(canvas, 86))

        def on_drag_handle(e):
            dx, dy = drag_delta(e)
            active_sig["x"] = max(0.05, min(0.95, active_sig["x"] + dx / float(cw)))
            active_sig["y"] = max(0.05, min(0.95, active_sig["y"] + dy / float(ch)))
            redraw()
            page.update()

        sig_handle.on_pan_update = on_drag_handle
        size_slider.on_change = lambda e: (active_sig.update({"w": float(size_slider.value)}), redraw(), page.update())

        def import_new_sig(_):
            app_data["picker_mode"] = "import_sig"
            pick_files_generic(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)

        def capture_sig_from_cam(_):
            open_camera_screen(new_doc=False, auto_crop=False, mode="sig")

        def save_sig_to_page(_):
            if not active_sig.get("file"):
                toast("⚠️ Hãy chụp hoặc chọn ảnh chữ ký trước!", Colors.ORANGE_800)
                return
            snapshot_doc(doc)
            pg["signatures"] = current_sig_list()

            def work():
                refresh_page_render(pg)
                save_page_meta(pg)

            run_bg(work, lambda _: (open_doc_studio(app_data["current_doc_idx"], keep_page=True),
                                    toast("✍️ Đã gắn chữ ký!")))

        def clear_sigs(_):
            snapshot_doc(doc)
            pg["signatures"] = []

            def work():
                refresh_page_render(pg)
                save_page_meta(pg)

            run_bg(work, lambda _: (open_doc_studio(app_data["current_doc_idx"], keep_page=True),
                                    toast("🗑️ Đã gỡ chữ ký!")))

        redraw()
        root_body.content = ft.Container(bgcolor=CS_DARK, expand=True, content=ft.Column([
            ft.Container(padding=pad_sym(8, 8), bgcolor="#11171A", content=ft.Row([
                ft.IconButton(Icons.ARROW_BACK, icon_color=WHITE,
                              on_click=lambda _: open_doc_studio(app_data["current_doc_idx"], keep_page=True)),
                ft.Text(f"Chèn Chữ Ký - Trang {p_idx + 1}", color=WHITE, weight=ft.FontWeight.BOLD, expand=True),
                Btn("Gắn ✓", bgcolor=CS_TEAL, color=WHITE, on_click=save_sig_to_page),
            ])),
            ft.Text("Kéo nút tròn ✥ để đặt chữ ký vào vị trí mong muốn", color="#B0BEC5", size=12),
            ft.Container(
                expand=True, alignment=ALIGN_CENTER,
                content=ft.Stack(width=cw, height=ch, controls=[sig_preview, sig_handle]),
            ),
            ft.Container(bgcolor="#11171A", padding=10, content=ft.Column([
                ft.Row([ft.Text("Độ lớn:", color=WHITE, size=12), size_slider]),
                ft.Row([
                    Btn("📸 Chụp Ký", bgcolor=CS_ORANGE, color=WHITE, on_click=capture_sig_from_cam),
                    Btn("🖼️ Chọn Ảnh", bgcolor=CS_TEAL, color=WHITE, on_click=import_new_sig),
                    OutBtn("🗑️ Gỡ", on_click=clear_sigs),
                ], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
            ], tight=True, spacing=6)),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True))
        page.update()

    # =================================================================
    # MÀN HÌNH 6: CAMERA ĐIỆN THOẠI (NÚT SHUTTER TRÒN LỚN Ở GIỮA ĐÁY)
    # =================================================================
    def open_camera_screen(new_doc=True, auto_crop=True, folder="Chung", mode="doc"):
        page.floating_action_button = None
        app_data["cam_running"] = True

        cam_state = {
            "cam_idx": 0,
            "cap": None,
            "last_raw": None,
            "captured_frames": [],
            "auto_guide": (mode == "doc" and auto_crop),
            "mirror": False,
            "rot": 0,
            "switching": False,
            "quad": None,
            "found_doc": False,
            "blur_val": 120.0,
            "lum_val": 140.0,
        }

        cam_view_img = make_img(expand=True, fit=FIT.CONTAIN)
        cam_status_txt = ft.Text("⏳ Đang mở Camera...", color="#A7FFEB", size=12, weight=ft.FontWeight.BOLD)
        cam_quality_txt = ft.Text("", color="#FFE082", size=11, weight=ft.FontWeight.BOLD)
        captured_strip = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=6, height=62)
        done_badge_txt = ft.Text("Lưu (0) ✓", color=WHITE, weight=ft.FontWeight.BOLD, size=13)

        def release_cam():
            app_data["cam_running"] = False
            cap = cam_state.get("cap")
            cam_state["cap"] = None
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

        def open_capture_device(idx):
            old = cam_state.get("cap")
            if old is not None:
                try:
                    old.release()
                except Exception:
                    pass
            cap = None
            try:
                if os.name == "nt" and hasattr(cv2, "CAP_DSHOW"):
                    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                    if not cap or not cap.isOpened():
                        cap = cv2.VideoCapture(idx)
                else:
                    cap = cv2.VideoCapture(idx)
                if cap and cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                    return cap
            except Exception:
                pass
            return None

        def fallback_system_picker(_=None):
            release_cam()
            if mode == "sig":
                app_data["picker_mode"] = "import_sig"
                pick_files_generic(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)
            else:
                import_state["new_doc"] = new_doc
                import_state["auto"] = auto_crop
                import_state["folder"] = folder
                app_data["picker_mode"] = "import_images"
                pick_files_generic(allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE)

        def refresh_captured_strip():
            captured_strip.controls.clear()
            n = len(cam_state["captured_frames"])
            done_badge_txt.value = f"Lưu ({n}) ✓"
            for idx_f, frm in enumerate(cam_state["captured_frames"]):
                th = fit_max(frm, 110)
                b64 = img_to_b64(th, 75)
                captured_strip.controls.append(
                    ft.Container(
                        width=50, height=58, padding=2, bgcolor="#263238", border_radius=6,
                        content=ft.Stack([
                            make_img(b64, width=46, height=54, fit=FIT.COVER),
                            ft.GestureDetector(
                                right=0, top=0,
                                on_tap=lambda e, i=idx_f: remove_captured(i),
                                content=ft.Container(
                                    width=16, height=16, bgcolor=Colors.RED_700, border_radius=8,
                                    alignment=ALIGN_CENTER,
                                    content=ft.Text("×", color=WHITE, size=10, weight=ft.FontWeight.BOLD),
                                ),
                            ),
                        ]),
                    )
                )

        def remove_captured(idx_f):
            if 0 <= idx_f < len(cam_state["captured_frames"]):
                cam_state["captured_frames"].pop(idx_f)
                refresh_captured_strip()
                page.update()

        def switch_camera(_):
            cam_state["cam_idx"] = (cam_state["cam_idx"] + 1) % 3
            cam_state["switching"] = True
            cam_status_txt.value = f"🔄 Đang chuyển Cam #{cam_state['cam_idx']}..."
            page.update()

        def snap_photo(_=None):
            raw = cam_state.get("last_raw")
            if raw is None:
                fallback_system_picker()
                return
            frame_copy = raw.copy()

            if mode == "sig":
                release_cam()

                def work_sig():
                    rgba = extract_signature_rgba(frame_copy)
                    fn = f"sig_{int(time.time())}.png"
                    write_png(os.path.join(SIG_DIR, fn), rgba)
                    return fn

                def done_sig(fn):
                    doc = cur_doc()
                    pg = doc["pages"][app_data["active_page_idx"]]
                    pg.setdefault("signatures", []).append(
                        {"file": fn, "x": 0.72, "y": 0.82, "w": 0.30, "opacity": 0.95}
                    )
                    open_signature_screen(app_data["active_page_idx"])
                    toast("✍️ Đã chụp & tách nền chữ ký!")

                run_bg(work_sig, done_sig)
                return

            cam_state["captured_frames"].append(frame_copy)
            refresh_captured_strip()
            q_check = analyze_image_quality(frame_copy)
            if q_check["is_blur"]:
                toast(f"⚠️ Trang #{len(cam_state['captured_frames'])} hơi MỜ! Bấm × trên ảnh nhỏ nếu muốn chụp lại.", Colors.ORANGE_900)
            else:
                toast(f"📸 Đã chụp trang #{len(cam_state['captured_frames'])}!")
            page.update()

        def finish_capture(_=None):
            frames = list(cam_state["captured_frames"])
            if not frames:
                toast("⚠️ Hãy bấm nút tròn ở giữa để chụp ít nhất 1 trang!", Colors.ORANGE_800)
                return
            use_crop = bool(cam_state["auto_guide"])
            release_cam()

            def work():
                out = []
                for idx_f, frm in enumerate(frames):
                    out.append(
                        create_page_from_raw(
                            frm,
                            auto_crop=use_crop,
                            name=f"Cam_{time.strftime('%H%M%S')}_{idx_f + 1}.jpg",
                        )
                    )
                return out

            def done(new_pages):
                if new_doc or app_data["current_doc_idx"] < 0 or not app_data["docs"]:
                    doc = new_doc_record(f"Scan Camera #{len(app_data['docs']) + 1}", new_pages, folder=folder)
                    app_data["docs"].insert(0, doc)
                    save_doc(doc)
                    open_doc_studio(0)
                else:
                    doc = cur_doc()
                    doc["pages"].extend(new_pages)
                    doc["undo"].clear()
                    save_doc(doc)
                    open_doc_studio(app_data["current_doc_idx"], keep_page=True)
                toast(f"🎯 Đã lưu {len(new_pages)} trang!")

            run_bg(work, done)

        def cancel_camera(_=None):
            release_cam()
            if mode == "sig":
                open_signature_screen(app_data["active_page_idx"])
            elif not new_doc and app_data["current_doc_idx"] >= 0 and app_data["docs"]:
                open_doc_studio(app_data["current_doc_idx"], keep_page=True)
            else:
                render_home_view()

        def camera_loop():
            cap = open_capture_device(cam_state["cam_idx"])
            if cap is None and cam_state["cam_idx"] != 0:
                cam_state["cam_idx"] = 0
                cap = open_capture_device(0)
            cam_state["cap"] = cap

            if cap is None:
                cam_status_txt.value = "📱 Chế độ Máy ảnh Hệ thống"
                cam_quality_txt.value = "Bấm nút tròn màu cam bên dưới để mở Máy ảnh / Thư viện của thiết bị"
                try:
                    page.update()
                except Exception:
                    pass
                return

            cam_status_txt.value = f"🟢 Cam #{cam_state['cam_idx']}"
            frame_counter = 0

            while app_data.get("cam_running", False):
                if cam_state.get("switching"):
                    cam_state["switching"] = False
                    new_cap = open_capture_device(cam_state["cam_idx"])
                    if new_cap is None:
                        cam_state["cam_idx"] = 0
                        new_cap = open_capture_device(0)
                    cam_state["cap"] = new_cap
                    cap = new_cap
                    if cap is None:
                        break
                    cam_status_txt.value = f"🟢 Cam #{cam_state['cam_idx']}"

                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.05)
                    continue

                if cam_state["mirror"]:
                    frame = cv2.flip(frame, 1)
                rot = cam_state["rot"] % 360
                if rot == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif rot == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif rot == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                cam_state["last_raw"] = frame
                disp = fit_max(frame, 640).copy()
                dh, dw = disp.shape[:2]

                frame_counter += 1
                if frame_counter % 4 == 0:
                    gray_s = cv2.cvtColor(disp, cv2.COLOR_BGR2GRAY)
                    cam_state["blur_val"] = float(cv2.Laplacian(gray_s, cv2.CV_64F).var())
                    cam_state["lum_val"] = float(np.mean(gray_s))
                    if cam_state["auto_guide"]:
                        quad, found = detect_document_quad(disp)
                        cam_state["quad"] = quad
                        cam_state["found_doc"] = found
                    else:
                        cam_state["found_doc"] = False

                if cam_state["auto_guide"] and cam_state.get("quad") is not None and cam_state.get("found_doc"):
                    pts = np.array(cam_state["quad"], dtype=np.int32)
                    overlay = disp.copy()
                    cv2.fillPoly(overlay, [pts], (160, 220, 0))
                    cv2.addWeighted(overlay, 0.18, disp, 0.82, 0, disp)
                    cv2.polylines(disp, [pts], True, (0, 230, 118), 3, cv2.LINE_AA)
                elif mode == "sig":
                    sx1, sy1 = int(dw * 0.12), int(dh * 0.30)
                    sx2, sy2 = int(dw * 0.88), int(dh * 0.70)
                    cv2.rectangle(disp, (sx1, sy1), (sx2, sy2), (0, 230, 118), 2)

                b_val, l_val = cam_state["blur_val"], cam_state["lum_val"]
                q_tags = ["⚠️ Rung tay" if b_val < 55 else "✅ Nét"]
                if l_val < 70:
                    q_tags.append("⚠️ Hơi tối")
                if cam_state["auto_guide"]:
                    q_tags.append("🎯 Đã bắt khung" if cam_state["found_doc"] else "🔍 Tìm mép giấy")
                cam_quality_txt.value = " • ".join(q_tags)

                set_img(cam_view_img, img_to_b64(disp, 78))
                try:
                    cam_view_img.update()
                    cam_quality_txt.update()
                except Exception:
                    page.update()

                time.sleep(0.035)

            release_cam()

        shutter_button = ft.GestureDetector(
            on_tap=snap_photo,
            content=ft.Container(
                width=72, height=72, border_radius=36,
                border=border_all(4, WHITE),
                padding=4,
                alignment=ALIGN_CENTER,
                content=ft.Container(width=56, height=56, border_radius=28, bgcolor=CS_ORANGE),
            ),
        )

        root_body.content = ft.Container(bgcolor="#0B0F12", expand=True, content=ft.Column([
            ft.Container(padding=pad_sym(8, 6), bgcolor="#11171A", content=ft.Row([
                ft.IconButton(Icons.CLOSE, icon_color=WHITE, on_click=cancel_camera),
                ft.Column([cam_status_txt, cam_quality_txt], spacing=1, expand=True,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.IconButton(Icons.ROTATE_90_DEGREES_CW, icon_color=WHITE, tooltip="Xoay khung ngắm",
                              on_click=lambda _: cam_state.update({"rot": (cam_state["rot"] + 90) % 360})),
                ft.IconButton(Icons.FLIP, icon_color=WHITE, tooltip="Lật gương",
                              on_click=lambda _: cam_state.update({"mirror": not cam_state["mirror"]})),
            ])),

            ft.Container(expand=True, alignment=ALIGN_CENTER, content=cam_view_img),

            ft.Container(padding=pad_sym(10, 2), content=captured_strip) if mode == "doc" else ft.Container(),

            ft.Container(
                bgcolor="#11171A",
                padding=pad_sym(18, 12),
                content=ft.Row([
                    ft.Container(
                        width=86, height=42, border_radius=21, bgcolor="#263238",
                        alignment=ALIGN_CENTER, on_click=switch_camera,
                        content=ft.Row([
                            ft.Icon(Icons.REFRESH, color=WHITE, size=18),
                            ft.Text("Đổi Cam", color=WHITE, size=12, weight=ft.FontWeight.BOLD),
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=4),
                    ),
                    shutter_button,
                    ft.Container(
                        width=86, height=42, border_radius=21, bgcolor=CS_TEAL,
                        alignment=ALIGN_CENTER,
                        on_click=finish_capture if mode == "doc" else snap_photo,
                        content=done_badge_txt if mode == "doc" else ft.Text("Chụp Ký", color=WHITE, size=12, weight=ft.FontWeight.BOLD),
                    ),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ),
        ], expand=True, spacing=0))
        page.update()

        threading.Thread(target=camera_loop, daemon=True).start()

    # =================================================================
    # 7. TẢI ẢNH LÊN & HỆ THỐNG FILE PICKER ĐA NỀN TẢNG (0.2x + 0.70+ APK)
    # =================================================================
    import_state = {"new_doc": True, "auto": True, "order": "name", "reverse": False, "folder": "Chung"}

    def handle_import_images(paths):
        if not paths:
            return
        auto, new_doc = import_state["auto"], import_state["new_doc"]
        order, rev = import_state["order"], import_state["reverse"]
        folder = import_state.get("folder", "Chung") or "Chung"

        def _mtime(path):
            try:
                return os.path.getmtime(path)
            except OSError:
                return 0

        paths = list(paths)
        if order == "name":
            paths.sort(key=lambda q: natural_key(os.path.basename(q)))
        elif order == "time":
            paths.sort(key=lambda q: (_mtime(q), natural_key(os.path.basename(q))))
        if rev:
            paths.reverse()

        def work():
            out = []
            for p in paths:
                raw = read_image_utf8(p)
                if raw is None:
                    continue
                out.append(create_page_from_raw(raw, auto_crop=auto, name=os.path.basename(p)))
            return out

        def done(new_pages):
            if not new_pages:
                toast("❌ Không đọc được file ảnh!", Colors.RED_700)
                return
            if new_doc or app_data["current_doc_idx"] < 0 or not app_data["docs"]:
                doc = new_doc_record(f"Tài liệu #{len(app_data['docs']) + 1}", new_pages, folder=folder)
                app_data["docs"].insert(0, doc)
                save_doc(doc)
                open_doc_studio(0)
            else:
                doc = cur_doc()
                doc["pages"].extend(new_pages)
                doc["undo"].clear()
                save_doc(doc)
                open_doc_studio(app_data["current_doc_idx"], keep_page=True)

            blur_list = [i + 1 for i, p in enumerate(new_pages) if p.get("is_blur")]
            dark_list = [i + 1 for i, p in enumerate(new_pages) if p.get("is_dark")]
            if blur_list or dark_list:
                msg_parts = []
                if blur_list:
                    msg_parts.append(f"{len(blur_list)} ảnh MỜ")
                if dark_list:
                    msg_parts.append(f"{len(dark_list)} ảnh TỐI")
                toast(f"⚠️ Phát hiện {' & '.join(msg_parts)}! Hãy kiểm tra các trang có dấu ⚠️.", Colors.ORANGE_900)
            else:
                toast(f"🎯 Đã xử lý {len(new_pages)} trang rõ nét!")

        run_bg(work, done)

    def handle_import_signature(paths):
        if not paths:
            return
        p = paths[0]

        def work():
            raw = read_image_utf8(p)
            if raw is None:
                raise ValueError("Không đọc được ảnh chữ ký!")
            rgba = extract_signature_rgba(raw)
            fn = f"sig_{int(time.time())}.png"
            write_png(os.path.join(SIG_DIR, fn), rgba)
            return fn

        def done(fn):
            doc = cur_doc()
            pg = doc["pages"][app_data["active_page_idx"]]
            pg.setdefault("signatures", []).append({"file": fn, "x": 0.72, "y": 0.82, "w": 0.30, "opacity": 0.95})
            open_signature_screen(app_data["active_page_idx"])
            toast("✍️ Đã tách nền chữ ký!")

        run_bg(work, done)

    def handle_restore_backup(paths):
        if not paths:
            return
        p = paths[0]

        def work():
            return restore_full_backup_zip(p)

        def done(cnt):
            app_data["docs"] = load_all_docs()
            app_data["trash"] = purge_and_load_trash()
            render_home_view()
            toast(f"📥 Đã khôi phục {cnt} bộ tài liệu!")

        run_bg(work, done)

    def dispatch_picked_files(paths):
        if not paths:
            return
        mode = app_data.get("picker_mode", "import_images")
        if mode == "import_sig":
            handle_import_signature(paths)
        elif mode == "restore_zip":
            handle_restore_backup(paths)
        else:
            handle_import_images(paths)

    # Khởi tạo FilePicker tương thích cả Flet 0.2x (overlay) và Flet 0.70+ (services async)
    old_picker = None
    new_picker = None

    if NEW_FLET:
        try:
            new_picker = ft.FilePicker()
            if hasattr(page, "services"):
                page.services.append(new_picker)
        except Exception:
            new_picker = None
    else:
        def on_old_picker_result(e):
            files = getattr(e, "files", None)
            if files:
                dispatch_picked_files([f.path for f in files if getattr(f, "path", None)])

        old_picker = ft.FilePicker(on_result=on_old_picker_result)
        page.overlay.append(old_picker)

    async def _pick_new_async(allow_multiple, file_type, allowed_extensions):
        picker = new_picker or ft.FilePicker()
        if hasattr(page, "services") and picker not in page.services:
            try:
                page.services.append(picker)
            except Exception:
                pass
        kw = {"allow_multiple": allow_multiple, "file_type": file_type}
        if allowed_extensions:
            kw["allowed_extensions"] = allowed_extensions
        files = await picker.pick_files(**kw)
        if files:
            dispatch_picked_files([f.path for f in files if getattr(f, "path", None)])

    def pick_files_generic(allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE, allowed_extensions=None):
        if NEW_FLET:
            page.run_task(_pick_new_async, allow_multiple, file_type, allowed_extensions)
        else:
            kw = {"allow_multiple": allow_multiple, "file_type": file_type}
            if allowed_extensions:
                kw["allowed_extensions"] = allowed_extensions
            old_picker.pick_files(**kw)

    def show_import_sheet(new_doc):
        import_state["new_doc"] = new_doc
        default_folder = app_data["active_folder"] if app_data["active_folder"] != "Tất cả" else "Chung"
        tf_folder = ft.TextField(value=default_folder, label="Lưu vào Thư mục", height=44, text_size=13)
        dd_order = ft.Dropdown(label="Thứ tự sắp xếp trang", value="name", options=[
            DDOpt(key="name", text="Theo tên file (IMG_1, IMG_2...)"),
            DDOpt(key="time", text="Theo thời gian chụp"),
            DDOpt(key="pick", text="Giữ nguyên thứ tự chọn")])

        def pick_now(auto_c):
            import_state["auto"] = auto_c
            import_state["order"] = dd_order.value or "name"
            import_state["folder"] = (tf_folder.value or "").strip() or "Chung"
            app_data["picker_mode"] = "import_images"
            close_dlg(bs)
            pick_files_generic(allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE)

        bs = ft.BottomSheet(ft.Container(padding=16, bgcolor=WHITE, border_radius=16, content=ft.Column([
            ft.Text("Chọn Ảnh Từ Thiết Bị", weight=ft.FontWeight.BOLD, size=15),
            tf_folder if new_doc else ft.Container(),
            dd_order,
            ft.Container(
                bgcolor="#E0F2F1", border_radius=12, padding=10,
                on_click=lambda _: pick_now(True),
                content=ft.Row([
                    ft.Icon(Icons.CROP_FREE, color=CS_TEAL, size=28),
                    ft.Column([
                        ft.Text("Tự động cắt nền bàn & làm phẳng (Khuyên dùng)", weight=ft.FontWeight.BOLD, size=13, color=CS_TEAL),
                        ft.Text("AI tự tìm 4 góc giấy, làm sáng & đo độ nét", size=11, color="#455A64"),
                    ], spacing=2, expand=True),
                ], spacing=10),
            ),
            ft.Container(
                bgcolor="#F5F7F9", border_radius=12, padding=10,
                on_click=lambda _: pick_now(False),
                content=ft.Row([
                    ft.Icon(Icons.IMAGE_OUTLINED, color="#546E7A", size=28),
                    ft.Column([
                        ft.Text("Giữ nguyên 100% khung ảnh gốc", weight=ft.FontWeight.BOLD, size=13),
                        ft.Text("Dành cho ảnh thẻ hoặc tài liệu đã cắt sẵn", size=11, color="#546E7A"),
                    ], spacing=2, expand=True),
                ], spacing=10),
            ),
        ], tight=True, spacing=8)))
        open_dlg(bs)

    page.add(ft.SafeArea(content=ft.Column([busy_bar, root_body], expand=True, spacing=0), expand=True))
    render_home_view()


if __name__ == "__main__":
    _runner = getattr(ft, "run", None) or getattr(ft, "app", None)
    try:
        _runner(main)
    except TypeError:
        _runner(target=main)
