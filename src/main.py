"""
CS Scanner Pro V5.0
- Lưu tài liệu bền vững (thoát app mở lại vẫn còn)
- Tiết kiệm RAM: ảnh gốc / ảnh đã cắt nằm trên đĩa, trong RAM chỉ giữ bản nhỏ
- Xuất PDF khổ A4 thật (150 / 200 / 300 DPI), tự viết PDF nên không tốn RAM
- Hoàn tác, sắp xếp lại thứ tự trang, ghép CCCD 2 mặt vào 1 trang A4
- Xử lý ảnh chạy nền (không đơ giao diện), xem trước dùng ảnh nhỏ cho nhanh
- Tương thích cả Flet cũ (0.2x) lẫn Flet mới (0.70+)
Yêu cầu: pip install flet opencv-python-headless numpy   (không còn cần Pillow)
"""
import base64
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid

import cv2
import flet as ft
import numpy as np

# =====================================================================
# 0. LỚP TƯƠNG THÍCH FLET CŨ / MỚI
# =====================================================================
Colors = getattr(ft, "Colors", None) or ft.colors
Icons = getattr(ft, "Icons", None) or ft.icons
FIT = getattr(ft, "BoxFit", None) or ft.ImageFit
IMG_OLD = hasattr(ft.Image, "src_base64")
NEW_FLET = hasattr(ft, "Service") or hasattr(ft, "Share")
OLD_PICKER = hasattr(ft, "FilePickerResultEvent") and not NEW_FLET
Btn = getattr(ft, "ElevatedButton", None) or ft.Button
OutBtn = getattr(ft, "OutlinedButton", None) or ft.Button
DDOpt = getattr(ft, "DropdownOption", None) or ft.dropdown.Option

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


def pm_item(label, cb):
    try:
        return ft.PopupMenuItem(text=label, on_click=cb)
    except TypeError:
        return ft.PopupMenuItem(content=label, on_click=cb)


def drag_delta(e):
    dx, dy = getattr(e, "delta_x", None), getattr(e, "delta_y", None)
    if dx is None or dy is None:
        d = getattr(e, "local_delta", None) or getattr(e, "global_delta", None)
        dx, dy = d.x, d.y
    return dx, dy


# =====================================================================
# 1. LƯU TRỮ TRÊN ĐĨA
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
            for sub in ("pages", "docs", "exports"):
                os.makedirs(os.path.join(root, sub), exist_ok=True)
            return root
        except Exception:
            continue
    raise RuntimeError("Không tạo được thư mục lưu dữ liệu")


DATA_DIR = _init_dirs()
PAGES_DIR = os.path.join(DATA_DIR, "pages")
DOCS_DIR = os.path.join(DATA_DIR, "docs")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")


def p_raw(pid): return os.path.join(PAGES_DIR, f"{pid}_raw.jpg")
def p_warp(pid): return os.path.join(PAGES_DIR, f"{pid}_warp.jpg")
def p_thumb(pid): return os.path.join(PAGES_DIR, f"{pid}_thumb.jpg")
def p_view(pid): return os.path.join(PAGES_DIR, f"{pid}_view.jpg")
def p_meta(pid): return os.path.join(PAGES_DIR, f"{pid}.json")
def d_meta(did): return os.path.join(DOCS_DIR, f"{did}.json")


def read_image_utf8(path: str):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def write_jpg(path: str, img, q: int = 93):
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(q)])
    buf.tofile(path)


def img_to_b64(img_bgr, quality: int = 88) -> str:
    _, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return base64.b64encode(buf).decode("utf-8")


def file_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def sanitize_filename(name: str, default: str = "Scan") -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name or "").strip(" ._")
    return name[:80] or default


def fit_max(img, max_side: int = 1600):
    h, w = img.shape[:2]
    s = max_side / float(max(h, w))
    if s < 1:
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
    """Ghi file vào Download (nếu được), không được thì vào thư mục exports của app."""
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
# 2. TỰ ĐỘNG TÁCH NỀN BÀN & CANH CHỈNH TỜ GIẤY
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


def auto_detect_corners(img_bgr):
    h, w = img_bgr.shape[:2]
    scale = 600.0 / max(h, w)
    small = cv2.resize(img_bgr, (int(w * scale), int(h * scale)))
    sh, sw = small.shape[:2]
    min_area = (sh * sw) * 0.15

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(gray, 11)
    blur = cv2.GaussianBlur(blur, (7, 7), 0)

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
        if area < min_area or area > (sh * sw * 0.98):
            continue
        hull = cv2.convexHull(c)
        peri = cv2.arcLength(hull, True)
        for eps in [0.015, 0.02, 0.03, 0.04, 0.05]:
            approx = cv2.approxPolyDP(hull, eps * peri, True)
            if len(approx) == 4:
                return order_points(approx.reshape(4, 2) / scale)
        if area > (sh * sw * 0.25):
            box_pts = cv2.boxPoints(cv2.minAreaRect(hull)) / scale
            return order_points(box_pts)

    return full_corners(w, h)


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


# =====================================================================
# 3. CHỈNH SÁNG NỀN & ĐẬM CHỮ
# =====================================================================
def apply_photoshop_levels(img, brightness: float, contrast: float, gamma: float = 1.0):
    white_point = int(max(135, min(255, 255 - brightness * 1.15)))
    black_point = int(max(0, min(125, contrast * 1.15)))
    if white_point <= black_point + 15:
        white_point = black_point + 15
    lut = np.zeros(256, dtype=np.uint8)
    span = float(white_point - black_point)
    for i in range(256):
        if i <= black_point:
            lut[i] = 0
        elif i >= white_point:
            lut[i] = 255
        else:
            norm = (i - black_point) / span
            lut[i] = int(min(255, max(0, (norm ** gamma) * 255.0)))
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


def process_page_image(warped_bgr, mode="clear_orig", brightness=38, contrast=35, sharpness=1.0, rotation=0):
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
    return out


# =====================================================================
# 4. BẢN GHI TRANG (ÍT RAM: ảnh nằm trên đĩa)
# =====================================================================
SETTING_KEYS = ("filter", "bright", "contrast", "sharp", "rotation", "selected")
DEFAULTS = {"filter": "clear_orig", "bright": 38, "contrast": 35, "sharp": 1.0, "rotation": 0, "selected": True}

_warp_cache = {}  # pid -> ảnh đã cắt (tối đa 3 trang trong RAM)


def get_warped(pg):
    pid = pg["id"]
    if pid in _warp_cache:
        return _warp_cache[pid]
    img = read_image_utf8(p_warp(pid))
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
    warped = fit_max(warp_document(raw, pg["corners"]), 3508)
    write_jpg(p_warp(pid), warped, 95)
    _warp_cache[pid] = warped
    while len(_warp_cache) > 3:
        _warp_cache.pop(next(iter(_warp_cache)))
    pg["prev"] = None


def refresh_page_render(pg):
    """Tạo lại ảnh nhỏ (thumb + view) từ bản xem nhanh 900px."""
    small = process_page_image(
        get_prev(pg), pg["filter"], pg["bright"], pg["contrast"], pg["sharp"], pg["rotation"]
    )
    h, w = small.shape[:2]
    thumb = cv2.resize(small, (220, max(1, int(220 * h / w))), interpolation=cv2.INTER_AREA)
    write_jpg(p_thumb(pg["id"]), thumb, 82)
    write_jpg(p_view(pg["id"]), small, 88)
    pg["thumb_b64"] = img_to_b64(thumb, 82)
    pg["view_b64"] = img_to_b64(small, 88)


def render_full(pg, max_side=None):
    warped = get_warped(pg)
    if max_side:
        warped = fit_max(warped, max_side)
    return process_page_image(warped, pg["filter"], pg["bright"], pg["contrast"], pg["sharp"], pg["rotation"])


def save_page_meta(pg):
    meta = {k: pg[k] for k in SETTING_KEYS}
    meta["id"] = pg["id"]
    meta["corners"] = np.asarray(pg["corners"]).tolist()
    meta["name"] = pg.get("name", "")
    with open(p_meta(pg["id"]), "w", encoding="utf-8") as f:
        json.dump(meta, f)


def natural_key(text):
    """Sắp xếp tự nhiên: IMG_2 đứng trước IMG_10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text or "")]


def limit_side(img, max_side=3000):
    return fit_max(img, max_side)


def create_page_from_raw(raw_bgr, auto_crop=True, corners=None, name="", **settings):
    pid = uuid.uuid4().hex[:10]
    raw = limit_side(raw_bgr, 3000)
    write_jpg(p_raw(pid), raw, 93)
    if corners is None:
        corners = auto_detect_corners(raw) if auto_crop else full_corners(raw.shape[1], raw.shape[0])
    pg = {"id": pid, "name": name, "corners": np.array(corners, dtype="float32"), "prev": None,
          "thumb_b64": "", "view_b64": ""}
    for k in SETTING_KEYS:
        pg[k] = settings.get(k, DEFAULTS[k])
    rebuild_warp(pg, raw)
    refresh_page_render(pg)
    save_page_meta(pg)
    return pg


def load_page(pid):
    try:
        with open(p_meta(pid), "r", encoding="utf-8") as f:
            meta = json.load(f)
        if not os.path.exists(p_warp(pid)):
            return None
        pg = {"id": pid, "name": meta.get("name", ""), "corners": np.array(meta["corners"], dtype="float32"), "prev": None,
              "thumb_b64": "", "view_b64": ""}
        for k in SETTING_KEYS:
            pg[k] = meta.get(k, DEFAULTS[k])
        if os.path.exists(p_thumb(pid)) and os.path.exists(p_view(pid)):
            pg["thumb_b64"] = file_to_b64(p_thumb(pid))
            pg["view_b64"] = file_to_b64(p_view(pid))
        else:
            refresh_page_render(pg)
        return pg
    except Exception:
        return None


def delete_page_files(pg):
    pid = pg["id"]
    _warp_cache.pop(pid, None)
    for p in (p_raw(pid), p_warp(pid), p_thumb(pid), p_view(pid), p_meta(pid)):
        try:
            os.remove(p)
        except OSError:
            pass


def save_doc(doc):
    data = {"id": doc["id"], "title": doc["title"], "date": doc["date"],
            "selected": doc.get("selected", False), "page_ids": [pg["id"] for pg in doc["pages"]]}
    with open(d_meta(doc["id"]), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def delete_doc_json(doc):
    try:
        os.remove(d_meta(doc["id"]))
    except OSError:
        pass


def delete_doc_all(doc):
    for pg in doc["pages"]:
        delete_page_files(pg)
    delete_doc_json(doc)


def new_doc_record(title, pages):
    return {"id": str(int(time.time() * 1000)), "title": title,
            "date": time.strftime("%d/%m/%Y %H:%M"), "selected": True, "pages": pages, "undo": []}


def load_all_docs():
    docs = []
    for fn in os.listdir(DOCS_DIR):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(DOCS_DIR, fn), "r", encoding="utf-8") as f:
                d = json.load(f)
            pages = [pg for pg in (load_page(pid) for pid in d.get("page_ids", [])) if pg]
            if not pages:
                continue
            docs.append({"id": d["id"], "title": d.get("title", "Tài liệu"), "date": d.get("date", ""),
                         "selected": d.get("selected", False), "pages": pages, "undo": []})
        except Exception:
            continue
    docs.sort(key=lambda d: int(d["id"]), reverse=True)
    return docs


# --- Hoàn tác ---
def snapshot_doc(doc):
    snap = []
    for pg in doc["pages"]:
        st = {k: pg[k] for k in SETTING_KEYS}
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
            pg[k] = st[k]
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
# 5. XUẤT FILE: PDF A4 TỰ VIẾT (KHÔNG TỐN RAM) + JPG
# =====================================================================
QUALITY = {"low": (150, 78), "mid": (200, 86), "high": (300, 92)}


def compose_pdf_page(img, dpi, paper):
    ih, iw = img.shape[:2]
    a4w, a4h = int(round(8.2677 * dpi)), int(round(11.693 * dpi))
    if iw > ih:
        a4w, a4h = a4h, a4w
    if paper == "a4":
        s = min(a4w / iw, a4h / ih)
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
    """items: list[(jpeg_bytes, w_px, h_px, dpi)] -> bytes PDF (mỗi trang là 1 ảnh JPEG)."""
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


def export_pages(pages, name, fmt, quality, paper):
    dpi, q = QUALITY.get(quality, QUALITY["mid"])
    base = sanitize_filename(name)
    if fmt == "pdf":
        items = []
        for pg in pages:
            canvas = compose_pdf_page(render_full(pg), dpi, paper)
            ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), q])
            h, w = canvas.shape[:2]
            items.append((buf.tobytes(), w, h, dpi))
        return [write_output(base + ".pdf", build_pdf(items))]
    paths = []
    for i, pg in enumerate(pages):
        ok, buf = cv2.imencode(".jpg", render_full(pg), [int(cv2.IMWRITE_JPEG_QUALITY), min(98, q + 6)])
        fn = f"{base}.jpg" if len(pages) == 1 else f"{base}_{i + 1}.jpg"
        paths.append(write_output(fn, buf.tobytes()))
    return paths


def compose_id_card(a, b, dpi=200):
    """Ghép 2 mặt giấy tờ (CCCD, GPLX...) vào 1 trang A4 dọc."""
    W, H = int(round(8.2677 * dpi)), int(round(11.693 * dpi))
    canvas = np.full((H, W, 3), 255, np.uint8)
    max_w, slot_h = int(W * 0.78), int(H * 0.36)
    for k, im in enumerate((a, b)):
        ih, iw = im.shape[:2]
        s = min(max_w / iw, slot_h / ih)
        r = cv2.resize(im, (max(1, int(iw * s)), max(1, int(ih * s))),
                       interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        cy = int(H * (0.27 if k == 0 else 0.72))
        y, x = cy - r.shape[0] // 2, (W - r.shape[1]) // 2
        canvas[y:y + r.shape[0], x:x + r.shape[1]] = r
        cv2.rectangle(canvas, (x, y), (x + r.shape[1] - 1, y + r.shape[0] - 1), (170, 170, 170), 2)
    return canvas


# =====================================================================
# 6. GIAO DIỆN
# =====================================================================
def main(page: ft.Page):
    page.title = "CS Scanner Pro V5.0"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.bgcolor = "#F0F3F5"
    try:
        page.window.width = 480
        page.window.height = 900
    except Exception:
        pass

    CS_TEAL, CS_DARK, CS_ACCENT = "#00897B", "#1E272C", "#00BFA5"
    WHITE = Colors.WHITE

    app_data = {"docs": [], "current_doc_idx": -1, "active_page_idx": 0,
                "crop_target_idx": -1, "crop_raw": None, "crop_disp": None,
                "busy": False, "pending": None}
    try:
        app_data["docs"] = load_all_docs()
    except Exception:
        app_data["docs"] = []

    root_body = ft.Container(expand=True)
    busy_bar = ft.ProgressBar(visible=False, color=CS_TEAL)

    FILTER_OPTIONS = [
        ("clear_orig", "🌟 Gốc Sáng Rõ"),
        ("flat_light", "☀️ Khử Bóng Nền"),
        ("crisp_gray", "📄 Chữ Đen Nét"),
        ("bw_print", "⚫ Đen Trắng"),
        ("raw", "🖼️ Ảnh Gốc"),
    ]

    def cur_doc():
        return app_data["docs"][app_data["current_doc_idx"]]

    # ---------- thông báo / hộp thoại ----------
    def toast(msg, color=CS_TEAL):
        sb = ft.SnackBar(content=ft.Text(msg, color=WHITE, weight=ft.FontWeight.BOLD), bgcolor=color, duration=3200)
        if hasattr(page, "show_dialog"):
            page.show_dialog(sb)
        else:
            page.snack_bar = sb
            sb.open = True
            page.update()

    def open_dlg(dlg):
        if hasattr(page, "show_dialog"):
            page.show_dialog(dlg)
        else:
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

    def close_dlg(dlg):
        if hasattr(page, "pop_dialog"):
            page.pop_dialog()
        else:
            dlg.open = False
            page.update()
            if dlg in page.overlay:
                page.overlay.remove(dlg)

    def confirm_dlg(title, msg, on_yes):
        def yes(e):
            close_dlg(dlg)
            on_yes()
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(title), content=ft.Text(msg),
            actions=[ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                     Btn("Đồng ý", bgcolor=Colors.RED_600, color=WHITE, on_click=yes)])
        open_dlg(dlg)

    # ---------- chạy nền ----------
    def run_bg(work, done=None, latest_wins=False):
        if app_data["busy"]:
            if latest_wins:
                app_data["pending"] = (work, done)
            else:
                toast("⏳ Đang xử lý, vui lòng đợi một chút...", Colors.ORANGE_800)
            return
        app_data["busy"] = True

        def _t():
            busy_bar.visible = True
            page.update()
            res, err = None, None
            try:
                res = work()
            except Exception as ex:
                err = ex
            app_data["busy"] = False
            busy_bar.visible = False
            try:
                if err is not None:
                    toast(f"❌ Lỗi xử lý: {err}", Colors.RED_700)
                elif done:
                    done(res)
            except Exception as ex:
                toast(f"❌ Lỗi giao diện: {ex}", Colors.RED_700)
            page.update()
            nxt, app_data["pending"] = app_data["pending"], None
            if nxt:
                run_bg(nxt[0], nxt[1], True)

        threading.Thread(target=_t, daemon=True).start()

    # ---------- chia sẻ ----------
    share_svc = None
    if hasattr(ft, "Share"):
        try:
            share_svc = ft.Share()
            if hasattr(page, "services"):
                page.services.append(share_svc)
        except Exception:
            share_svc = None

    def share_files(paths):
        if share_svc is None:
            toast(f"⚠️ Bản Flet này chưa có chia sẻ trực tiếp. File ở: {paths[0]}", Colors.ORANGE_800)
            return
        tmp = os.path.join(os.environ.get("FLET_APP_STORAGE_TEMP") or tempfile.gettempdir(), "cs_share")

        async def _do():
            try:
                os.makedirs(tmp, exist_ok=True)
                files = []
                for p in paths:
                    dst = os.path.join(tmp, os.path.basename(p))
                    shutil.copyfile(p, dst)
                    files.append(ft.ShareFile.from_path(dst))
                await share_svc.share_files(files, text="Tài liệu scan từ CS Scanner")
            except Exception as ex:
                toast(f"⚠️ Không mở được bảng chia sẻ ({ex}). File ở: {paths[0]}", Colors.ORANGE_800)

        try:
            page.run_task(_do)
        except Exception as ex:
            toast(f"⚠️ Không chia sẻ được ({ex}). File ở: {paths[0]}", Colors.ORANGE_800)

    # ---------- đổi tên ----------
    def rename_doc_dialog(doc_idx, after):
        doc = app_data["docs"][doc_idx]
        tf = ft.TextField(value=doc["title"], label="Tên tài liệu", autofocus=True)

        def save(e):
            name = (tf.value or "").strip()
            if not name:
                tf.error_text = "Tên không được để trống"
                page.update()
                return
            doc["title"] = name
            save_doc(doc)
            close_dlg(dlg)
            after()
            toast(f"✏️ Đã đổi tên: {name}")

        tf.on_submit = save
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("✏️ Đổi tên tài liệu"), content=tf,
            actions=[ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                     Btn("Lưu", bgcolor=CS_TEAL, color=WHITE, on_click=save)])
        open_dlg(dlg)

    # ---------- xuất file ----------
    def open_export_dialog(default_name, pages, fmt):
        pages = list(pages)
        if not pages:
            toast("⚠️ Không có trang nào để xuất!", Colors.ORANGE_800)
            return
        ext = ".pdf" if fmt == "pdf" else ".jpg"
        tf = ft.TextField(value=default_name, label="Tên file", suffix_text=ext, autofocus=True)
        dd_q = ft.Dropdown(label="Chất lượng", value="mid", options=[
            DDOpt(key="low", text="Nhỏ gọn · 150 DPI (gửi Zalo/email)"),
            DDOpt(key="mid", text="Cân bằng · 200 DPI"),
            DDOpt(key="high", text="Cao · 300 DPI (in ấn)")])
        dd_p = ft.Dropdown(label="Khổ giấy PDF", value="a4", options=[
            DDOpt(key="a4", text="A4 chuẩn (căn giữa)"),
            DDOpt(key="fit", text="Theo tỷ lệ ảnh gốc")])
        controls = [tf, dd_q] + ([dd_p] if fmt == "pdf" else []) + [
            ft.Text(f"{len(pages)} trang", size=11, color="#546E7A")]

        def do(share):
            name = (tf.value or "").strip()
            if not name:
                tf.error_text = "Hãy nhập tên file"
                page.update()
                return
            q, paper = dd_q.value or "mid", dd_p.value or "a4"
            close_dlg(dlg)

            def done(paths):
                mb = sum(os.path.getsize(p) for p in paths) / 1048576.0
                if share:
                    share_files(paths)
                else:
                    extra = f" (+{len(paths) - 1} file)" if len(paths) > 1 else ""
                    toast(f"✅ Đã lưu {mb:.1f} MB: {paths[0]}{extra}")

            run_bg(lambda: export_pages(pages, name, fmt, q, paper), done)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("📄 Xuất PDF" if fmt == "pdf" else "🖼️ Xuất ảnh JPG"),
            content=ft.Column(controls, tight=True, spacing=8),
            actions=[ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                     OutBtn("💾 Lưu", on_click=lambda _: do(False)),
                     Btn("📤 Lưu & Chia sẻ", bgcolor=CS_TEAL, color=WHITE, on_click=lambda _: do(True))],
            actions_alignment=ft.MainAxisAlignment.END)
        open_dlg(dlg)

    def export_selected_docs_pdf(e):
        sel = [d for d in app_data["docs"] if d.get("selected")]
        if not sel:
            toast("⚠️ Hãy tích chọn ít nhất 1 bộ tài liệu để xuất PDF!", Colors.ORANGE_800)
            return
        pages = [pg for d in sel for pg in d["pages"]]
        default = sel[0]["title"] if len(sel) == 1 else f"Scan_{time.strftime('%Y%m%d_%H%M')}"
        open_export_dialog(default, pages, "pdf")

    def export_current_doc_pdf(e):
        d = cur_doc()
        open_export_dialog(d["title"], d["pages"], "pdf")

    def export_current_doc_jpgs(e):
        d = cur_doc()
        open_export_dialog(d["title"], d["pages"], "jpg")

    # =================================================================
    # MÀN HÌNH XEM TRƯỚC
    # =================================================================
    pv = {"idx": 0, "compare": False}
    pv_holder = ft.Container(expand=True, bgcolor="#11171A", alignment=ALIGN_CENTER)
    pv_img = make_img(fit=FIT.CONTAIN)
    pv_title = ft.Text("", color=WHITE, size=13, weight=ft.FontWeight.BOLD, expand=True)
    pv_chips = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=6)
    pv_bright = ft.Slider(min=0, max=85, divisions=17, value=38, label="Độ sáng nền: {value}", active_color=CS_ACCENT)
    pv_contrast = ft.Slider(min=0, max=85, divisions=17, value=35, label="Độ đậm chữ: {value}", active_color=CS_ACCENT)
    pv_compare_btn = OutBtn("")

    def render_preview_b64(pg, compare):
        warped = fit_max(get_warped(pg), 1500)
        if compare:
            src = process_page_image(warped, "raw", 0, 0, 0.0, pg["rotation"])
        else:
            src = process_page_image(warped, pg["filter"], pg["bright"], pg["contrast"], pg["sharp"], pg["rotation"])
        return img_to_b64(src, 92)

    def pv_render(reset_zoom=False):
        doc = cur_doc()
        pages = doc["pages"]
        pv["idx"] = max(0, min(pv["idx"], len(pages) - 1))
        pg = pages[pv["idx"]]
        tag = "  [ẢNH GỐC]" if pv["compare"] else ""
        pv_title.value = f"Trang {pv['idx'] + 1}/{len(pages)}{tag}"
        pv_compare_btn.text = "👁 Đang xem: Gốc (bấm để xem bản đã chỉnh)" if pv["compare"] else "👁 So sánh với ảnh gốc"
        pv_chips.controls.clear()
        for code, label in FILTER_OPTIONS:
            on = pg["filter"] == code
            pv_chips.controls.append(Btn(label, bgcolor=CS_TEAL if on else "#37474F", color=WHITE,
                                         on_click=lambda e, c=code: pv_adjust(new_filter=c)))
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
        pg = doc["pages"][pv["idx"]]
        pv_bright.value, pv_contrast.value = pg["bright"], pg["contrast"]
        pv["compare"] = False
        pv_render(reset_zoom=True)

    def pv_adjust(new_filter=None):
        doc = cur_doc()
        pg = doc["pages"][pv["idx"]]
        snapshot_doc(doc)
        b, c = int(pv_bright.value), int(pv_contrast.value)
        pv["compare"] = False

        def work():
            if new_filter is not None:
                pg["filter"] = new_filter
            pg["bright"], pg["contrast"] = b, c
            refresh_page_render(pg)
            save_page_meta(pg)
            return render_preview_b64(pg, False)

        def done(b64):
            set_img(pv_img, b64)
            pv_title.value = f"Trang {pv['idx'] + 1}/{len(doc['pages'])}"
            pv_chips.controls.clear()
            for code, label in FILTER_OPTIONS:
                on = pg["filter"] == code
                pv_chips.controls.append(Btn(label, bgcolor=CS_TEAL if on else "#37474F", color=WHITE,
                                             on_click=lambda e, cc=code: pv_adjust(new_filter=cc)))
            page.update()

        run_bg(work, done, latest_wins=True)

    def pv_toggle_compare(e):
        pv["compare"] = not pv["compare"]
        pv_render()

    def close_preview(e=None):
        app_data["active_page_idx"] = pv["idx"]
        open_doc_studio(app_data["current_doc_idx"], keep_page=True)

    pv_bright.on_change_end = lambda e: pv_adjust()
    pv_contrast.on_change_end = lambda e: pv_adjust()
    pv_compare_btn.on_click = pv_toggle_compare

    def open_preview(p_idx):
        page.floating_action_button = None
        root_body.content = ft.Column([
            ft.Container(bgcolor="#11171A", padding=pad_sym(6, 6), content=ft.Row([
                ft.IconButton(Icons.ARROW_BACK, icon_color=WHITE, on_click=close_preview),
                pv_title,
                ft.IconButton(Icons.CHEVRON_LEFT, icon_color=WHITE, on_click=lambda _: pv_goto(pv["idx"] - 1)),
                ft.IconButton(Icons.CHEVRON_RIGHT, icon_color=WHITE, on_click=lambda _: pv_goto(pv["idx"] + 1)),
            ])),
            pv_holder,
            ft.Container(bgcolor="#1E272C", padding=10, content=ft.Column([
                ft.Text("Chụm 2 ngón để phóng to, kiểm tra chữ có rõ không", size=11, color="#B0BEC5"),
                pv_chips,
                ft.Text("☀️ Độ sáng nền", size=11, color=WHITE), pv_bright,
                ft.Text("✒️ Độ đậm chữ", size=11, color=WHITE), pv_contrast,
                pv_compare_btn,
            ], spacing=2, tight=True)),
        ], expand=True, spacing=0)
        pv_goto(p_idx)

    # =================================================================
    # MÀN HÌNH 1: TRANG CHỦ
    # =================================================================
    docs_list_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    def toggle_all_docs(state):
        for d in app_data["docs"]:
            d["selected"] = state
            save_doc(d)
        render_home_view()

    def delete_selected_docs(e):
        sel = [d for d in app_data["docs"] if d.get("selected")]
        if not sel:
            toast("⚠️ Chưa tích chọn tài liệu nào!", Colors.ORANGE_800)
            return

        def go():
            for d in sel:
                delete_doc_all(d)
            app_data["docs"] = [d for d in app_data["docs"] if not d.get("selected")]
            render_home_view()
            toast(f"🗑️ Đã xóa {len(sel)} bộ tài liệu!")

        confirm_dlg("Xóa tài liệu?", f"Xóa vĩnh viễn {len(sel)} bộ tài liệu đang tích chọn?", go)

    def merge_selected_docs(e):
        sel = [d for d in app_data["docs"] if d.get("selected")]
        if len(sel) < 2:
            toast("⚠️ Hãy tích chọn ít nhất 2 bộ tài liệu để gộp chung!", Colors.ORANGE_800)
            return
        combined = [pg for d in sel for pg in d["pages"]]
        nd = new_doc_record("Tài liệu gộp", combined)
        for d in sel:
            delete_doc_json(d)  # giữ nguyên file ảnh vì trang chuyển sang bộ mới
        app_data["docs"] = [d for d in app_data["docs"] if not d.get("selected")]
        app_data["docs"].insert(0, nd)
        save_doc(nd)
        render_home_view()
        toast(f"📑 Đã gộp thành 1 bộ gồm {len(combined)} trang!")

    def open_batch_dialog():
        sel = [d for d in app_data["docs"] if d.get("selected")]
        if not sel:
            toast("Hãy tích chọn ít nhất 1 tài liệu!", Colors.ORANGE_800)
            return
        dd = ft.Dropdown(label="Bộ lọc áp dụng hàng loạt", value="clear_orig",
                         options=[DDOpt(key=k, text=v) for k, v in FILTER_OPTIONS])
        sb = ft.Slider(min=0, max=85, divisions=17, value=38, label="Độ sáng nền: {value}")
        sc = ft.Slider(min=0, max=85, divisions=17, value=35, label="Độ đậm chữ: {value}")

        def apply(e):
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

            run_bg(work, lambda n: (render_home_view(), toast(f"✨ Đã chỉnh sáng & làm đậm cho {n} trang!")))

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("🎨 Chỉnh Sáng & Đậm Hàng Loạt"),
            content=ft.Column([
                ft.Text("Áp dụng cho các bộ tài liệu đang tích chọn:", size=12), dd,
                ft.Text("☀️ Tăng độ sáng (làm trắng nền giấy):", size=12, weight=ft.FontWeight.BOLD), sb,
                ft.Text("✒️ Tăng độ đậm (làm đen nét chữ):", size=12, weight=ft.FontWeight.BOLD), sc,
            ], tight=True, spacing=6),
            actions=[ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                     Btn("Áp dụng ngay ✓", bgcolor=CS_TEAL, color=WHITE, on_click=apply)])
        open_dlg(dlg)

    def render_home_view():
        try:
            fab = ft.FloatingActionButton(icon=Icons.ADD_PHOTO_ALTERNATE, text="Tải Ảnh Lên (Tự Cắt Nền)",
                                          bgcolor=CS_TEAL, on_click=lambda _: show_import_sheet(True))
        except TypeError:
            fab = ft.FloatingActionButton(icon=Icons.ADD_PHOTO_ALTERNATE,
                                          content=ft.Text("Tải Ảnh Lên (Tự Cắt Nền)", color=WHITE),
                                          bgcolor=CS_TEAL, on_click=lambda _: show_import_sheet(True))
        page.floating_action_button = fab
        docs_list_col.controls.clear()
        sel_count = sum(1 for d in app_data["docs"] if d.get("selected"))

        if not app_data["docs"]:
            docs_list_col.controls.append(ft.Container(height=380, alignment=ALIGN_CENTER, content=ft.Column([
                ft.Icon(Icons.DOCUMENT_SCANNER_ROUNDED, size=76, color="#B0BEC5"),
                ft.Text("Chưa có tài liệu nào", size=17, weight=ft.FontWeight.BOLD, color="#546E7A"),
                ft.Text("Bấm 'Tải Ảnh Lên' để tự động cắt bỏ nền bàn & làm sáng giấy", size=12, color="#78909C"),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER)))
        else:
            for idx, doc in enumerate(app_data["docs"]):
                thumb = doc["pages"][0]["thumb_b64"] if doc["pages"] else ""

                def on_chk(e, i=idx):
                    app_data["docs"][i]["selected"] = e.control.value
                    save_doc(app_data["docs"][i])
                    render_home_view()

                docs_list_col.controls.append(ft.Card(elevation=2, content=ft.Container(padding=6, content=ft.Row([
                    ft.Checkbox(value=doc.get("selected", False), active_color=CS_TEAL, on_change=on_chk),
                    ft.GestureDetector(on_tap=lambda e, i=idx: open_doc_studio(i), content=ft.Row([
                        make_img(thumb, width=48, height=64, fit=FIT.COVER, border_radius=4),
                        ft.Column([
                            ft.Text(doc["title"], weight=ft.FontWeight.BOLD, size=14),
                            ft.Text(f"📅 {doc['date']}  •  📄 {len(doc['pages'])} trang", size=11, color="#546E7A"),
                        ], spacing=2)], spacing=10)),
                    ft.Container(expand=True),
                    ft.IconButton(Icons.DRIVE_FILE_RENAME_OUTLINE, icon_color="#546E7A", tooltip="Đổi tên",
                                  on_click=lambda e, i=idx: rename_doc_dialog(i, render_home_view)),
                    ft.IconButton(Icons.EDIT_DOCUMENT, icon_color=CS_TEAL, tooltip="Mở chỉnh sửa",
                                  on_click=lambda e, i=idx: open_doc_studio(i)),
                ]))))

        root_body.content = ft.Column([
            ft.Container(bgcolor=CS_TEAL, padding=pad_sym(16, 12), content=ft.Row([
                ft.Row([ft.Icon(Icons.DOCUMENT_SCANNER, color=WHITE, size=24),
                        ft.Text("CS Scanner Pro V5.0", color=WHITE, size=19, weight=ft.FontWeight.BOLD)]),
                ft.Text(f"Đã chọn: {sel_count}/{len(app_data['docs'])}", color="#A7FFEB", size=12,
                        weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)),
            ft.Container(bgcolor=WHITE, padding=pad_sym(10, 6), content=ft.Row([
                ft.TextButton("☑️ Tất cả", on_click=lambda _: toggle_all_docs(True)),
                ft.TextButton("⬜ Bỏ chọn", on_click=lambda _: toggle_all_docs(False)),
                Btn("🎨 Chỉnh Sáng", bgcolor="#00695C", color=WHITE, on_click=lambda _: open_batch_dialog()),
                OutBtn("📑 Gộp", on_click=merge_selected_docs),
                OutBtn("📄 Xuất PDF", on_click=export_selected_docs_pdf),
                ft.IconButton(Icons.DELETE_OUTLINE, icon_color=Colors.RED_600, on_click=delete_selected_docs),
            ], scroll=ft.ScrollMode.AUTO, spacing=4)),
            ft.Container(padding=pad_sym(12, 4), expand=True, content=docs_list_col),
        ], expand=True, spacing=4)
        page.update()

    # =================================================================
    # MÀN HÌNH 2: STUDIO
    # =================================================================
    big_preview_img = make_img(height=280, fit=FIT.CONTAIN)
    page_strip_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)
    selection_status_txt = ft.Text("", size=12, weight=ft.FontWeight.BOLD, color=CS_TEAL)
    bright_slider = ft.Slider(min=0, max=85, divisions=17, value=38, label="Độ sáng nền: {value}", active_color=CS_TEAL)
    contrast_slider = ft.Slider(min=0, max=85, divisions=17, value=35, label="Độ đậm chữ: {value}", active_color=CS_TEAL)
    sharp_slider = ft.Slider(min=0.0, max=2.5, divisions=10, value=1.0, label="Độ sắc nét: {value}", active_color=CS_TEAL)
    filter_chips_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=6)
    apply_all_switch = ft.Switch(label="Áp dụng cùng lúc cho tất cả trang đang tích chọn ☑️", value=True,
                                 active_color=CS_TEAL)

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
                h, w = raw.shape[:2]
                pg["corners"] = auto_detect_corners(raw) if use_ai else full_corners(w, h)
                rebuild_warp(pg, raw)
                refresh_page_render(pg)
                save_page_meta(pg)

        run_bg(work, lambda _: (refresh_studio_ui(),
                                toast("🎯 Đã tự động canh chỉnh vào trang giấy!" if use_ai
                                      else "🖼️ Đã khôi phục toàn bộ khung ảnh gốc!")))

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
        toast("🔤 Đã sắp xếp theo tên file gốc" if mode == "name" else "🔃 Đã đảo ngược thứ tự")

    def move_to_dialog(e=None):
        doc = cur_doc()
        n = len(doc["pages"])
        tf = ft.TextField(label=f"Vị trí mới (từ 1 đến {n})", keyboard_type=ft.KeyboardType.NUMBER,
                          autofocus=True)

        def go(ev):
            try:
                j = int((tf.value or "").strip())
            except ValueError:
                j = 0
            if not 1 <= j <= n:
                tf.error_text = f"Nhập số từ 1 đến {n}"
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
            modal=True, title=ft.Text("↔ Chuyển trang đang xem tới vị trí"), content=tf,
            actions=[ft.TextButton("Hủy", on_click=lambda _: close_dlg(dlg)),
                     Btn("Chuyển", bgcolor=CS_TEAL, color=WHITE, on_click=go)])
        open_dlg(dlg)

    def undo_last(e=None):
        doc = cur_doc()
        if not doc["undo"]:
            toast("Không còn thao tác nào để hoàn tác", Colors.ORANGE_800)
            return
        snap = doc["undo"].pop()
        run_bg(lambda: restore_snapshot(doc, snap),
               lambda _: (select_active_page(app_data["active_page_idx"]), toast("↩️ Đã hoàn tác")))

    def delete_selected_pages(e):
        doc = cur_doc()
        sel = [pg for pg in doc["pages"] if pg.get("selected")]
        removed = sel if sel else ([doc["pages"][app_data["active_page_idx"]]] if doc["pages"] else [])
        if not removed:
            return

        def go():
            rm_ids = {pg["id"] for pg in removed}
            for pg in removed:
                delete_page_files(pg)
            doc["pages"] = [pg for pg in doc["pages"] if pg["id"] not in rm_ids]
            doc["undo"].clear()
            if not doc["pages"]:
                delete_doc_json(doc)
                app_data["docs"].pop(app_data["current_doc_idx"])
                render_home_view()
                return
            save_doc(doc)
            select_active_page(min(app_data["active_page_idx"], len(doc["pages"]) - 1))
            toast(f"🗑️ Đã xóa {len(removed)} trang!")

        confirm_dlg("Xóa trang?", f"Xóa vĩnh viễn {len(removed)} trang? (không hoàn tác được)", go)

    def merge_id_card(e):
        doc = cur_doc()
        sel = [pg for pg in doc["pages"] if pg.get("selected")]
        if len(sel) != 2:
            toast("🪪 Hãy tích chọn đúng 2 trang (mặt trước và mặt sau)", Colors.ORANGE_800)
            return
        a, b = sel

        def work():
            canvas = compose_id_card(render_full(a, 1600), render_full(b, 1600))
            return create_page_from_raw(canvas, auto_crop=False, filter="raw", sharp=0.0)

        def done(newpg):
            ids = [p["id"] for p in doc["pages"]]
            pos = max(ids.index(a["id"]), ids.index(b["id"])) + 1
            a["selected"] = b["selected"] = False
            save_page_meta(a)
            save_page_meta(b)
            doc["pages"].insert(pos, newpg)
            doc["undo"].clear()
            save_doc(doc)
            app_data["active_page_idx"] = pos
            select_active_page(pos)
            toast("🪪 Đã ghép 2 mặt vào 1 trang A4!")

        run_bg(work, done)

    def refresh_studio_ui():
        doc = cur_doc()
        if not doc["pages"]:
            render_home_view()
            return
        p_idx = max(0, min(app_data["active_page_idx"], len(doc["pages"]) - 1))
        app_data["active_page_idx"] = p_idx
        cur = doc["pages"][p_idx]
        set_img(big_preview_img, cur["view_b64"])
        sel_cnt = sum(1 for pg in doc["pages"] if pg.get("selected"))
        selection_status_txt.value = (f"Trang {p_idx + 1}/{len(doc['pages'])}  •  Đang tích: {sel_cnt} trang"
                                      f"  •  Hoàn tác: {len(doc['undo'])}")
        filter_chips_row.controls.clear()
        for code, label in FILTER_OPTIONS:
            on = cur["filter"] == code
            filter_chips_row.controls.append(Btn(
                label, bgcolor=CS_TEAL if on else "#CFD8DC", color=WHITE if on else "#263238",
                on_click=lambda e, c=code: apply_adjustment_to_targets(new_filter=c)))
        page_strip_row.controls.clear()
        for i, pg in enumerate(doc["pages"]):
            viewing = i == p_idx
            page_strip_row.controls.append(ft.Container(
                width=95, padding=4, border_radius=8,
                bgcolor="#E0F2F1" if viewing else WHITE,
                border=border_all(3 if viewing else 1, CS_TEAL if viewing else "#B0BEC5"),
                content=ft.Column([
                    ft.Row([ft.Checkbox(value=pg.get("selected", False), active_color=CS_TEAL,
                                        on_change=lambda e, idx=i: toggle_page_checkbox(idx, e.control.value)),
                            ft.Text(f"#{i + 1}", size=11, weight=ft.FontWeight.BOLD)],
                           spacing=0, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.GestureDetector(on_tap=lambda e, idx=i: select_active_page(idx),
                                       content=make_img(pg["thumb_b64"], width=78, height=85, fit=FIT.COVER)),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER)))
        page.update()

    def open_doc_studio(doc_idx, keep_page=False):
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

        tools = ft.Row([
            Btn("📐 4 Góc Tay", bgcolor="#FFF3E0", color="#E65100",
                on_click=lambda _: open_crop_screen(app_data["active_page_idx"])),
            ft.IconButton(Icons.CROP_FREE, tooltip="AI tự cắt bỏ nền bàn", icon_color=CS_TEAL,
                          on_click=lambda _: batch_auto_crop_targets(True)),
            ft.IconButton(Icons.FULLSCREEN, tooltip="Khôi phục khung ảnh gốc",
                          on_click=lambda _: batch_auto_crop_targets(False)),
            ft.IconButton(Icons.ROTATE_RIGHT, tooltip="Xoay 90°",
                          on_click=lambda _: apply_adjustment_to_targets(rotate_delta=90)),
            ft.IconButton(Icons.UNDO, tooltip="Hoàn tác", icon_color="#3949AB", on_click=undo_last),
            ft.IconButton(Icons.ARROW_CIRCLE_LEFT_OUTLINED, tooltip="Dời trang sang trái",
                          on_click=lambda _: move_active_page(-1)),
            ft.IconButton(Icons.ARROW_CIRCLE_RIGHT_OUTLINED, tooltip="Dời trang sang phải",
                          on_click=lambda _: move_active_page(1)),
            ft.PopupMenuButton(icon=Icons.SORT, icon_color="#3949AB", tooltip="Sắp xếp trang", items=[
                pm_item("↔ Chuyển trang này tới vị trí số...", move_to_dialog),
                pm_item("🔤 Sắp xếp theo tên file gốc", lambda _: sort_pages("name")),
                pm_item("🔃 Đảo ngược toàn bộ thứ tự", lambda _: sort_pages("reverse")),
            ]),
            ft.IconButton(Icons.DELETE_OUTLINE, icon_color=Colors.RED_600, tooltip="Xóa trang",
                          on_click=delete_selected_pages),
        ], scroll=ft.ScrollMode.AUTO, spacing=2)

        root_body.content = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True, spacing=6, controls=[
            ft.Container(bgcolor=CS_TEAL, padding=pad_sym(8, 8), content=ft.Row([
                ft.IconButton(Icons.ARROW_BACK, icon_color=WHITE, on_click=lambda _: render_home_view()),
                ft.Text(doc["title"], color=WHITE, size=15, weight=ft.FontWeight.BOLD, expand=True,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.IconButton(Icons.DRIVE_FILE_RENAME_OUTLINE, icon_color=WHITE, tooltip="Đổi tên tài liệu",
                              on_click=lambda _: rename_doc_dialog(
                                  app_data["current_doc_idx"],
                                  lambda: open_doc_studio(app_data["current_doc_idx"], keep_page=True))),
                ft.IconButton(Icons.SHARE, icon_color=WHITE, tooltip="Xuất PDF & chia sẻ",
                              on_click=export_current_doc_pdf),
                ft.PopupMenuButton(icon=Icons.MORE_VERT, icon_color=WHITE, items=[
                    pm_item("📄 Xuất PDF...", export_current_doc_pdf),
                    pm_item("🖼️ Xuất ảnh JPG...", export_current_doc_jpgs),
                ]),
            ], spacing=0)),

            ft.Container(margin=mar_sym(10, 0), padding=8, bgcolor=WHITE, border_radius=10, content=ft.Column([
                selection_status_txt,
                tools,
                ft.GestureDetector(on_tap=lambda _: open_preview(app_data["active_page_idx"]),
                                   content=ft.Container(alignment=ALIGN_CENTER, content=big_preview_img)),
                Btn("🔍 Xem trước toàn màn hình (kiểm tra dễ đọc)", bgcolor="#263238", color=WHITE,
                    on_click=lambda _: open_preview(app_data["active_page_idx"])),
            ], spacing=4)),

            ft.Container(margin=mar_sym(10, 0), padding=8, bgcolor=WHITE, border_radius=10, content=ft.Column([
                ft.Row([
                    ft.Row([ft.TextButton("☑️ Chọn hết", on_click=lambda _: set_all_pages_checkbox(True)),
                            ft.TextButton("⬜ Bỏ chọn", on_click=lambda _: set_all_pages_checkbox(False))],
                           spacing=0),
                    Btn("➕ Tải Thêm Ảnh", bgcolor=CS_TEAL, color=WHITE,
                        on_click=lambda _: show_import_sheet(False)),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                OutBtn("🪪 Ghép CCCD / giấy tờ 2 mặt (tích chọn đúng 2 trang)", on_click=merge_id_card),
                page_strip_row,
            ], spacing=4)),

            ft.Container(margin=mar_sym(10, 0), padding=12, bgcolor=WHITE, border_radius=10, content=ft.Column([
                apply_all_switch,
                OutBtn("🔍 Xem thử trang này", on_click=lambda _: open_preview(app_data["active_page_idx"])),
                ft.Text("1. Chế độ màu (mặc định: '🌟 Gốc Sáng Rõ'):", size=12, weight=ft.FontWeight.BOLD),
                filter_chips_row,
                ft.Divider(height=8),
                ft.Row([ft.Icon(Icons.WB_SUNNY_OUTLINED, color="#FB8C00", size=20),
                        ft.Text("Độ sáng (làm trắng nền giấy):", size=12, weight=ft.FontWeight.BOLD)]),
                bright_slider,
                ft.Row([ft.Icon(Icons.CONTRAST, color=CS_TEAL, size=20),
                        ft.Text("Độ đậm (làm đen rõ nét chữ & chữ ký):", size=12, weight=ft.FontWeight.BOLD)]),
                contrast_slider,
                ft.Row([ft.Icon(Icons.AUTO_FIX_HIGH, color="#3949AB", size=20),
                        ft.Text("Độ sắc nét viền chữ:", size=12, weight=ft.FontWeight.BOLD)]),
                sharp_slider,
            ], spacing=4)),
        ])
        page.update()

    # =================================================================
    # MÀN HÌNH 3: KÉO 4 GÓC THỦ CÔNG
    # =================================================================
    CROP_W, CROP_H = 350, 450
    crop_bg_image = make_img(width=CROP_W, height=CROP_H, fit=FIT.FILL)
    crop_ui = {"pts": [[20, 20], [330, 20], [330, 430], [20, 430]], "sx": 1.0, "sy": 1.0}
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
        set_img(crop_bg_image, img_to_b64(disp, 80))

    def drag_corner_point(e, idx):
        dx, dy = drag_delta(e)
        nx = max(0, min(CROP_W, crop_ui["pts"][idx][0] + dx))
        ny = max(0, min(CROP_H, crop_ui["pts"][idx][1] + dy))
        crop_ui["pts"][idx] = [nx, ny]
        corner_handles[idx].left = nx - 18
        corner_handles[idx].top = ny - 18
        update_crop_canvas()
        page.update()

    for i in range(4):
        corner_handles.append(ft.GestureDetector(
            left=0, top=0, on_pan_update=lambda e, ci=i: drag_corner_point(e, ci),
            content=ft.Container(width=36, height=36, border_radius=18, bgcolor="#8800BFA5",
                                 border=border_all(3, WHITE), alignment=ALIGN_CENTER,
                                 content=ft.Container(width=10, height=10, border_radius=5, bgcolor="#FF1744"))))

    def sync_corners_to_handles(real_corners):
        h, w = app_data["crop_raw"].shape[:2]
        crop_ui["sx"], crop_ui["sy"] = w / float(CROP_W), h / float(CROP_H)
        for i in range(4):
            cx, cy = float(real_corners[i][0]) / crop_ui["sx"], float(real_corners[i][1]) / crop_ui["sy"]
            crop_ui["pts"][i] = [cx, cy]
            corner_handles[i].left, corner_handles[i].top = cx - 18, cy - 18
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
                                toast("📐 Đã cắt bỏ nền ngoài và làm phẳng trang giấy!")))

    def open_crop_screen(p_idx):
        doc = cur_doc()
        pg = doc["pages"][p_idx]
        app_data["crop_target_idx"] = p_idx
        raw = read_image_utf8(p_raw(pg["id"]))
        app_data["crop_raw"] = raw
        app_data["crop_disp"] = cv2.resize(raw, (CROP_W, CROP_H), interpolation=cv2.INTER_AREA)
        sync_corners_to_handles(pg["corners"])

        def full(_):
            h, w = app_data["crop_raw"].shape[:2]
            sync_corners_to_handles(full_corners(w, h))
            page.update()

        def ai(_):
            sync_corners_to_handles(auto_detect_corners(app_data["crop_raw"]))
            page.update()

        root_body.content = ft.Container(bgcolor=CS_DARK, expand=True, content=ft.Column([
            ft.Container(padding=10, bgcolor="#11171A", content=ft.Row([
                ft.TextButton("← Quay lại", style=ft.ButtonStyle(color=WHITE),
                              on_click=lambda _: open_doc_studio(app_data["current_doc_idx"], keep_page=True)),
                ft.Text(f"Chỉnh 4 Góc - Trang {p_idx + 1}", color=WHITE, weight=ft.FontWeight.BOLD),
                Btn("Cắt Phẳng ✓", bgcolor=CS_TEAL, color=WHITE, on_click=apply_crop_to_page),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)),
            ft.Text("Kéo 4 nút tròn đặt vào 4 góc tờ giấy trên nền bàn", color="#B0BEC5", size=12),
            ft.Container(expand=True, alignment=ALIGN_CENTER,
                         content=ft.Stack(width=CROP_W, height=CROP_H, controls=[crop_bg_image] + corner_handles)),
            ft.Container(bgcolor="#11171A", padding=10, content=ft.Row([
                ft.TextButton("🖼️ Lấy nguyên ảnh gốc", style=ft.ButtonStyle(color=WHITE), on_click=full),
                ft.TextButton("🎯 AI Tự bắt góc giấy", style=ft.ButtonStyle(color=CS_ACCENT), on_click=ai),
            ], alignment=ft.MainAxisAlignment.SPACE_AROUND)),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True))
        page.update()

    # =================================================================
    # 7. TẢI ẢNH LÊN
    # =================================================================
    import_state = {"new_doc": True, "auto": True, "order": "name", "reverse": False}

    def handle_import(paths):
        if not paths:
            return
        auto, new_doc = import_state["auto"], import_state["new_doc"]
        order, rev = import_state["order"], import_state["reverse"]

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
                try:
                    raw = read_image_utf8(p)
                except Exception:
                    continue
                if raw is None:
                    continue
                out.append(create_page_from_raw(raw, auto_crop=auto, name=os.path.basename(p)))
            return out

        def done(new_pages):
            if not new_pages:
                toast("Không đọc được file ảnh!", Colors.RED_700)
                return
            if new_doc or app_data["current_doc_idx"] < 0 or not app_data["docs"]:
                doc = new_doc_record(f"Tài liệu #{len(app_data['docs']) + 1}", new_pages)
                app_data["docs"].insert(0, doc)
                save_doc(doc)
                open_doc_studio(0)
            else:
                doc = cur_doc()
                doc["pages"].extend(new_pages)
                doc["undo"].clear()
                save_doc(doc)
                open_doc_studio(app_data["current_doc_idx"], keep_page=True)
            toast(f"🎯 Đã xử lý & lưu {len(new_pages)} trang!")

        run_bg(work, done)

    old_picker = None
    if OLD_PICKER:
        def on_old_result(e):
            if e.files:
                handle_import([f.path for f in e.files if f.path])

        old_picker = ft.FilePicker(on_result=on_old_result)
        page.overlay.append(old_picker)

    new_picker = None
    if not OLD_PICKER:
        try:
            new_picker = ft.FilePicker()
            if hasattr(page, "services"):
                page.services.append(new_picker)
        except Exception:
            new_picker = None

    async def _pick_new():
        picker = new_picker or ft.FilePicker()
        files = await picker.pick_files(allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE)
        handle_import([f.path for f in (files or []) if getattr(f, "path", None)])

    def pick_images():
        if OLD_PICKER:
            old_picker.pick_files(allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE)
        else:
            page.run_task(_pick_new)

    def show_import_sheet(new_doc):
        import_state["new_doc"] = new_doc
        crop_chk = ft.Switch(label="Tự động cắt bỏ nền bàn & kéo thẳng trang giấy", value=True, active_color=CS_TEAL)

        dd_order = ft.Dropdown(label="Thứ tự các trang khi tải lên", value="name", options=[
            DDOpt(key="name", text="Theo tên file (IMG_001, IMG_002...)"),
            DDOpt(key="time", text="Theo thời gian chụp / lưu file"),
            DDOpt(key="pick", text="Giữ nguyên thứ tự máy trả về")])
        rev_chk = ft.Switch(label="Đảo ngược thứ tự (chụp từ mới đến cũ)", value=False, active_color=CS_TEAL)

        def pick_now(auto_c):
            import_state["auto"] = auto_c
            import_state["order"] = dd_order.value or "name"
            import_state["reverse"] = bool(rev_chk.value)
            close_dlg(bs)
            pick_images()

        bs = ft.BottomSheet(ft.Container(padding=20, bgcolor=WHITE, content=ft.Column([
            ft.Text("Tải Ảnh Lên (chọn 1 hoặc nhiều ảnh)", weight=ft.FontWeight.BOLD, size=16),
            crop_chk,
            dd_order,
            rev_chk,
            ft.ListTile(leading=ft.Icon(Icons.CROP_FREE, color=CS_TEAL, size=32),
                        title=ft.Text("Tải ảnh & tự động cắt bỏ nền ngoài (khuyên dùng)", weight=ft.FontWeight.BOLD),
                        subtitle=ft.Text("Tự nhận diện 4 góc tờ giấy, cắt mặt bàn và làm phẳng"),
                        on_click=lambda _: pick_now(crop_chk.value)),
            ft.ListTile(leading=ft.Icon(Icons.IMAGE_OUTLINED, color="#546E7A", size=32),
                        title=ft.Text("Tải ảnh & giữ nguyên khung gốc 100%"),
                        subtitle=ft.Text("Dành cho ảnh đã được cắt sẵn"),
                        on_click=lambda _: pick_now(False)),
        ], tight=True, spacing=6)), open=True)
        open_dlg(bs)

    page.add(ft.SafeArea(content=ft.Column([busy_bar, root_body], expand=True, spacing=0), expand=True))
    render_home_view()


if __name__ == "__main__":
    runner = getattr(ft, "run", None) or ft.app
    try:
        runner(main)
    except TypeError:
        ft.app(target=main)
