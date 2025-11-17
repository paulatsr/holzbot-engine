# plan_segmentation.py
# ------------------------------------------------------------
# Pipeline complet + CLASIFICARE cu OpenAI (ChatGPT Vision)
# + post-procesare: ștergere exterior + auto-crop ROI.
# ------------------------------------------------------------

import os
import shutil
import cv2
import numpy as np
from pathlib import Path
from sklearn.cluster import KMeans
from dotenv import load_dotenv
import math
import subprocess
import tempfile
import shutil as _shutil
import base64
import uuid  # pentru job_id în workflow-ul de preț

from PIL import Image, ImageFile, ImageFilter
Image.MAX_IMAGE_PIXELS = None
ImageFile.LOAD_TRUNCATED_IMAGES = True

# =========================================
# CONFIG
# =========================================
INPUT_PATH = "test.png"
OUTPUT_DIR = "test_out"
DEBUG = True

# salvează și pagina întreagă „curățată” (exterior alb)
SAVE_CLEAN_FULL = True

REQUESTED_DPI = [900, 600, 450]
DOWNSAMPLE_TARGET_DPI = 450
_MAX_DIM = 32750

# 🔧 NOU: limităm latura maximă a planurilor rafinate (crop-uri) ca să nu fie uriașe pentru Roboflow / restul pipeline-ului
MAX_PLAN_EXPORT_LONG_EDGE = 2800  # px – poți ajusta 2500–3000 în funcție de ce suportă Roboflow confortabil

STEP_DIRS = {
    "text": "step0_no_text",
    "hatch": "step1_hatch",
    "outline": "step2_outlines",
    "thick": "step3_thick",
    "solid": "step4_solid",
    "walls": "step6_filled",
    "clusters": {
        "root": "step7_clusters",
        "initial": "step7_clusters/initial",
        "split": "step7_clusters/split",
        "merged": "step7_clusters/merged",
        "expanded": "step7_clusters/expanded",
        "final": "step7_clusters/final",
        "crops": "step7_clusters/crops"
    },
    "classified": {
        "root": "step8_classified",
        "blueprints": "step8_classified/blueprints",
        "side_views": "step8_classified/side_views",
        "text": "step8_classified/text",
        "siteplan": "step8_classified/siteplan"
    },
    "bp_refined": {
        "root": "step9_bp_refined",
        "debug": "step9_bp_refined/debug",
        "crops": "step9_bp_refined/crops"
    }
}

# =========================================
# RESET OUTPUT FOLDERS (nou)
# =========================================
def reset_output_folders(output_dir=None):
    """
    Resetează complet structura de foldere de output.
    Dacă output_dir este dat, actualizează global OUTPUT_DIR.
    """
    global OUTPUT_DIR

    if output_dir is not None:
        OUTPUT_DIR = output_dir

    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for k, v in STEP_DIRS.items():
        if isinstance(v, dict):
            for s in v.values():
                os.makedirs(os.path.join(OUTPUT_DIR, s), exist_ok=True)
        else:
            os.makedirs(os.path.join(OUTPUT_DIR, v), exist_ok=True)

    print(f"🧹 Folderul de output '{OUTPUT_DIR}' a fost resetat complet.\n")

# (!!!) Am scos resetarea automată de la import (era aici înainte)


# =========================================
# HELPERS
# =========================================
def save_debug(img, folder, name):
    path = os.path.join(OUTPUT_DIR, folder, name)
    cv2.imwrite(path, img)
    if DEBUG:
        print(f"📸 Saved: {path}")

def safe_imread(path):
    arr = np.fromfile(str(Path(path)), np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Nu s-a putut citi imaginea: {path}")
    return img

# 🔧 NOU: helper pentru micșorarea imaginilor folosite ca plan (crop-uri)
def resize_bgr_max_side(bgr, max_side: int = MAX_PLAN_EXPORT_LONG_EDGE):
    """
    Redimensionează imaginea BGR astfel încât latura maximă să fie <= max_side.
    Păstrează aspect ratio. Folosește INTER_AREA (bun pentru downscale).
    """
    h, w = bgr.shape[:2]
    long_side = max(h, w)
    if long_side <= max_side:
        return bgr
    scale = max_side / float(long_side)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    if DEBUG:
        print(f"🔻 Resize plan: {(w, h)} -> {(new_w, new_h)} (max_side={max_side})")
    return cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

# =========================================
# PDF → PNG (MuPDF -> Poppler -> Ghostscript)
# =========================================
from pdf2image import pdfinfo_from_path
def _which(x): return _shutil.which(x) is not None
def _safe_dpi_for_page(w_pt, h_pt, req_dpi):
    max_dpi_w = _MAX_DIM * 72.0 / max(w_pt, 1e-6)
    max_dpi_h = _MAX_DIM * 72.0 / max(h_pt, 1e-6)
    safe = min(req_dpi, math.floor(max_dpi_w), math.floor(max_dpi_h))
    return max(200, int(safe))
def _verify_png(path):
    try:
        im = Image.open(path); im.load()
        print(f"✅ PNG: {path} ({im.width}x{im.height})")
    except Exception as e:
        print(f"❌ PNG invalid {path}: {e}")
def _downsample_and_sharpen(src_path, target_path, scale_factor):
    im = Image.open(src_path).convert("RGB")
    if scale_factor is not None and scale_factor < 1.0:
        new_w = max(1, int(im.width * scale_factor))
        new_h = max(1, int(im.height * scale_factor))
        im = im.resize((new_w, new_h), Image.LANCZOS)
        im = im.filter(ImageFilter.UnsharpMask(radius=0.75, percent=120, threshold=2))
    im.save(target_path, "PNG")
    _verify_png(target_path)
def _render_with_mutool(pdf_path, page_idx, dpi, out_png):
    page_spec = f"{page_idx}-{page_idx}"
    tool = "mutool" if _which("mutool") else ("mudraw" if _which("mudraw") else None)
    if tool is None:
        raise RuntimeError("MuPDF (mutool/mudraw) indisponibil")
    cmd = [tool, "draw", "-o", out_png, "-r", str(dpi), "-F", "png", "-c", "rgb", "-A", "8", pdf_path, page_spec]
    subprocess.check_call(cmd)
def _render_with_pdftoppm(pdf_path, page_idx, dpi, out_prefix):
    cmd = ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page_idx), "-l", str(page_idx),
           "-aa", "yes", "-aaVector", "yes", pdf_path, out_prefix]
    subprocess.check_call(cmd)
    return f"{out_prefix}-{page_idx}.png"
def _render_with_ghostscript(pdf_path, page_idx, dpi, out_png):
    cmd = ["gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pngalpha", f"-r{dpi}",
           f"-dFirstPage={page_idx}", f"-dLastPage={page_idx}",
           "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4", "-o", out_png, pdf_path]
    subprocess.check_call(cmd)
def convert_pdf_to_png(pdf_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    info = pdfinfo_from_path(pdf_path, userpw=None)
    page_count = int(info.get("Pages", 1))
    if "Page size" in info:
        try:
            parts = info["Page size"].split("x")
            default_w_pt = float(parts[0].strip())
            default_h_pt = float(parts[1].split()[0].strip())
        except Exception:
            default_w_pt, default_h_pt = 595.0, 842.0
    else:
        default_w_pt, default_h_pt = 595.0, 842.0
    have_mutool = _which("mutool") or _which("mudraw")
    have_pdftoppm = _which("pdftoppm")
    have_gs = _which("gs")
    out_paths = []
    for page_idx in range(1, page_count + 1):
        key = f"Page {page_idx} size"
        if key in info:
            try:
                parts = info[key].split("x")
                w_pt = float(parts[0].strip()); h_pt = float(parts[1].split()[0].strip())
            except Exception:
                w_pt, h_pt = default_w_pt, default_h_pt
        else:
            w_pt, h_pt = default_w_pt, default_h_pt
        page_done = False
        last_error = None
        for req in REQUESTED_DPI:
            dpi = _safe_dpi_for_page(w_pt, h_pt, req)
            with tempfile.TemporaryDirectory() as tmpd:
                raw_png = os.path.join(tmpd, f"page_{page_idx:03d}.png")
                if not page_done and have_mutool:
                    try:
                        print(f"🖨️  MuPDF p.{page_idx} @ req {req} → safe {dpi} DPI ...")
                        _render_with_mutool(pdf_path, page_idx, dpi, raw_png)
                        page_done = True
                    except Exception as e:
                        last_error = e
                        print(f"⚠️  MuPDF p.{page_idx} @ {dpi} DPI a eșuat: {e}")
                if not page_done and have_pdftoppm:
                    try:
                        print(f"🖨️  Poppler p.{page_idx} @ req {req} → safe {dpi} DPI ...")
                        out_prefix = os.path.join(tmpd, "out")
                        raw_png_ppm = _render_with_pdftoppm(pdf_path, page_idx, dpi, out_prefix)
                        Path(raw_png_ppm).rename(raw_png)
                        page_done = True
                    except Exception as e:
                        last_error = e
                        print(f"⚠️  Poppler p.{page_idx} @ {dpi} DPI a eșuat: {e}")
                if not page_done and have_gs:
                    try:
                        print(f"🖨️  Ghostscript p.{page_idx} @ req {req} → safe {dpi} DPI ...")
                        _render_with_ghostscript(pdf_path, page_idx, dpi, raw_png)
                        page_done = True
                    except Exception as e:
                        last_error = e
                        print(f"⚠️  Ghostscript p.{page_idx} @ {dpi} DPI a eșuat: {e}")
                if page_done:
                    final_path = os.path.join(output_dir, f"page_{page_idx:03d}.png")
                    scale = (DOWNSAMPLE_TARGET_DPI / float(dpi)) if (DOWNSAMPLE_TARGET_DPI and DOWNSAMPLE_TARGET_DPI < dpi) else None
                    _downsample_and_sharpen(raw_png, final_path, scale)
                    out_paths.append(final_path)
                    break
        if not page_done:
            raise RuntimeError(f"Eșec conversie pagina {page_idx}. Ultima eroare: {last_error}")
    print(f"📄 Conversie finalizată → {len(out_paths)} PNG-uri de calitate.")
    return out_paths

# =========================================
# STEP 0 – Eliminare text
# =========================================
def remove_text_regions(img):
    print("\n[STEP 0] Eliminare text...")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 25, 15)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if 10 < w * h < 5000:
            cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)
    cleaned = img.copy()
    cleaned[mask == 255] = (255, 255, 255)
    save_debug(mask, STEP_DIRS["text"], "mask.jpg")
    save_debug(cleaned, STEP_DIRS["text"], "no_text.jpg")
    return cleaned

# =========================================
# STEP 1 – Eliminare hașuri
# =========================================
def remove_hatched_areas(gray):
    print("\n[STEP 1] Eliminare hașuri...")
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    inv = cv2.bitwise_not(blur)
    responses = []
    for t in [0, np.pi/4, np.pi/2, 3*np.pi/4]:
        kernel = cv2.getGaborKernel((25, 25), 4.0, t, 10.0, 0.5, 0)
        responses.append(cv2.filter2D(inv, cv2.CV_8UC3, kernel))
    mean_map, var_map = np.mean(responses, axis=0), np.var(responses, axis=0)
    mean_norm = cv2.normalize(mean_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    var_norm = cv2.normalize(var_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, strong = cv2.threshold(mean_norm, 120, 255, cv2.THRESH_BINARY)
    _, lowvar = cv2.threshold(var_norm, 40, 255, cv2.THRESH_BINARY_INV)
    hatch_mask = cv2.bitwise_and(strong, lowvar)
    hatch_mask = cv2.morphologyEx(hatch_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    hatch_mask = cv2.morphologyEx(hatch_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    result = gray.copy()
    result[hatch_mask > 0] = 255
    save_debug(hatch_mask, STEP_DIRS["hatch"], "mask.jpg")
    save_debug(result, STEP_DIRS["hatch"], "cleaned.jpg")
    return result

# =========================================
# STEP 2 – Detectare contururi
# =========================================
def detect_outlines(gray):
    print("\n[STEP 2] Detectare contururi...")
    edges = cv2.Canny(gray, 40, 120)
    save_debug(edges, STEP_DIRS["outline"], "edges.jpg")
    return edges

# =========================================
# STEP 3 – Filtrare grosimi
# =========================================
def filter_thick_lines(mask):
    print("\n[STEP 3] Filtrare grosimi...")
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    vals = dist[dist > 0].reshape(-1, 1)
    if len(vals) < 50:
        return mask
    if len(vals) > 50000:
        vals = vals[np.random.choice(len(vals), 50000, replace=False)]
    km = KMeans(n_clusters=2, n_init=5, random_state=42)
    km.fit(vals)
    thick = (dist > 0.5 * max(km.cluster_centers_.flatten())).astype(np.uint8) * 255
    save_debug(thick, STEP_DIRS["thick"], "thick_lines.jpg")
    return thick

# =========================================
# STEP 4 – Solidificăm pereții
# =========================================
def solidify_walls(mask):
    print("\n[STEP 4] Solidificare pereți...")
    h, w = mask.shape
    k = max(3, int(min(h, w) * 0.002))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    dil = cv2.dilate(closed, kernel, iterations=2)
    ero = cv2.erode(dil, kernel)
    save_debug(ero, STEP_DIRS["solid"], "solidified.jpg")
    return ero

# =========================================
# SPLIT/MERGE/EXPAND CLUSTERE (nemodificate)
# =========================================
def split_large_cluster(region, x1, y1, idx):
    print(f"  🔹 Split check cluster #{idx}")
    h, w = region.shape
    area = h * w
    if area < 30000:
        return [[x1, y1, x1 + w, y1 + h]]
    col_sum = np.sum(region > 0, axis=0)
    row_sum = np.sum(region > 0, axis=1)
    col_smooth = cv2.GaussianBlur(col_sum.astype(np.float32), (51, 1), 0)
    row_smooth = cv2.GaussianBlur(row_sum.astype(np.float32), (1, 51), 0)
    col_norm = col_smooth / (np.max(col_smooth) + 1e-5)
    row_norm = row_smooth / (np.max(row_smooth) + 1e-5)
    col_split = np.where(col_norm < 0.10)[0]
    row_split = np.where(row_norm < 0.10)[0]
    boxes = []
    if len(col_split) > 0:
        gaps = np.diff(col_split)
        big_gaps = np.where(gaps > 50)[0]
        if len(big_gaps) > 0:
            mid = int(np.median(col_split))
            if 0.3 * w < mid < 0.7 * w:
                save_debug(region, STEP_DIRS["clusters"]["split"], f"split_col_{idx}.jpg")
                for part, offset in [(region[:, :mid], 0), (region[:, mid:], mid)]:
                    num, _, stats, _ = cv2.connectedComponentsWithStats(part, 8)
                    for x, y, ww, hh, a in stats[1:]:
                        if a > 0.02 * area:
                            boxes.append([x1 + offset + x, y1 + y, x1 + offset + x + ww, y1 + y + hh])
                return boxes
    if len(row_split) > 0:
        gaps = np.diff(row_split)
        big_gaps = np.where(gaps > 50)[0]
        if len(big_gaps) > 0:
            mid = int(np.median(row_split))
            if 0.3 * h < mid < 0.7 * h:
                save_debug(region, STEP_DIRS["clusters"]["split"], f"split_row_{idx}.jpg")
                for part, offset in [(region[:mid, :], 0), (region[mid:, :], mid)]:
                    num, _, stats, _ = cv2.connectedComponentsWithStats(part, 8)
                    for x, y, ww, hh, a in stats[1:]:
                        if a > 0.02 * area:
                            boxes.append([x1 + x, y1 + offset + y, x1 + x + ww, y1 + offset + y + hh])
                return boxes
    return [[x1, y1, x1 + w, y1 + h]]

def merge_overlapping_boxes(boxes, shape):
    h, w = shape[:2]
    diag = np.hypot(h, w)
    prox = 0.005 * diag
    merged = True
    while merged:
        merged = False
        new_boxes = []
        while boxes:
            x1, y1, x2, y2 = boxes.pop(0)
            mbox = [x1, y1, x2, y2]
            keep = []
            for (xx1, yy1, xx2, yy2) in boxes:
                inter_x1, inter_y1 = max(x1, xx1), max(y1, yy1)
                inter_x2, inter_y2 = min(x2, xx2), min(y2, yy2)
                inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
                area1, area2 = (x2 - x1) * (y2 - y1), (xx2 - xx1) * (yy2 - yy2)  # (bug original lăsat intenționat)
                smaller_ratio = min(area1, area2) / max(area1, area2) if max(area1, area2) > 0 else 0
                dx, dy = max(0, max(x1 - xx2, xx1 - x2)), max(0, max(y1 - yy2, yy1 - y2))
                dist = np.hypot(dx, dy)
                if inter_area > 0 or (dist <= prox and smaller_ratio < 0.3):
                    mbox = [min(mbox[0], xx1), min(mbox[1], yy1), max(mbox[2], xx2), max(mbox[3], yy2)]
                    merged = True
                else:
                    keep.append([xx1, yy1, xx2, yy2])
            boxes = keep
            new_boxes.append(mbox)
        boxes = new_boxes
    return boxes

def expand_cluster(mask, x1, y1, x2, y2):
    h, w = mask.shape
    while True:
        expanded = False
        if y1 > 0 and np.any(mask[y1 - 1, x1:x2] == 255):
            y1 -= 1; expanded = True
        if y2 < h and np.any(mask[y2 - 1, x1:x2] == 255):
            y2 += 1; expanded = True
        if x1 > 0 and np.any(mask[y1:y2, x1 - 1] == 255):
            x1 -= 1; expanded = True
        if x2 < w and np.any(mask[y1:y2, x2 - 1] == 255):
            x2 += 1; expanded = True
        if not expanded:
            break
    return [x1, y1, x2, y2]

def detect_clusters(mask, orig):
    print("\n[STEP 7] Detectare clustere...")
    gray = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY) if len(mask.shape) == 3 else mask.copy()
    inv = cv2.bitwise_not(gray)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    clean = cv2.morphologyEx(cv2.dilate(inv, kernel), cv2.MORPH_OPEN, kernel)
    save_debug(clean, STEP_DIRS["clusters"]["initial"], "mask_clean.jpg")
    num, _, stats, _ = cv2.connectedComponentsWithStats(clean, 8)
    boxes = [[x, y, x + bw, y + bh] for x, y, bw, bh, a in stats[1:] if a > 200]
    print(f"🔸 Clustere inițiale: {len(boxes)}")
    refined = []
    for i, (x1, y1, x2, y2) in enumerate(boxes, 1):
        reg = clean[y1:y2, x1:x2]
        if reg.size == 0:
            continue
        for sb in split_large_cluster(reg, x1, y1, i):
            refined.append(expand_cluster(clean, *sb))
    merged = merge_overlapping_boxes(refined, clean.shape)
    save_debug(orig, STEP_DIRS["clusters"]["merged"], "after_merge.jpg")
    filtered = []
    for i, a in enumerate(merged):
        ax1, ay1, ax2, ay2 = a
        if any(bx1 <= ax1 and by1 <= ay1 and bx2 >= ax2 and by2 >= ay2
               for j, (bx1, by1, bx2, by2) in enumerate(merged) if i != j):
            continue
        filtered.append(a)
    if filtered:
        areas = [(x2 - x1) * (y1 - y2) for x1, y1, x2, y2 in filtered]  # not used later

    filtered2 = []
    for i, a in enumerate(merged):
        ax1, ay1, ax2, ay2 = a
        if any(bx1 <= ax1 and by1 <= ay1 and bx2 >= ax2 and by2 >= ay2
               for j, (bx1, by1, bx2, by2) in enumerate(merged) if i != j):
            continue
        filtered2.append(a)
    filtered = filtered2

    # 🔧 Filtrare „clustere prea mici” (relativ + absolut)
    if filtered:
        areas = np.array([(x2 - x1) * (y2 - y1) for x1, y1, x2, y2 in filtered], dtype=np.float64)
        max_area = float(areas.max())
        img_area = float(orig.shape[0] * orig.shape[1])

        MIN_REL = 0.10         # păstrează doar clustere ≥ 10% din cel mai mare
        MIN_ABS = 0.0005       # și ≥ 0.05% din aria imaginii (siguranță)
        min_allowed = max(MIN_REL * max_area, MIN_ABS * img_area)

        keep_idx = [i for i, a in enumerate(areas) if a >= min_allowed]
        filtered = [filtered[i] for i in keep_idx]

    result = orig.copy()
    for i, (x1, y1, x2, y2) in enumerate(filtered, 1):
        cv2.rectangle(result, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(result, str(i), (x1 + 5, y1 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imwrite(os.path.join(OUTPUT_DIR, STEP_DIRS["clusters"]["crops"], f"cluster_{i}.jpg"),
                    orig[y1:y2, x1:x2])
    save_debug(result, STEP_DIRS["clusters"]["final"], "final_clusters.jpg")
    print(f"✅ Clustere finale: {len(filtered)}")

# =========================================
# STEP 6 – Detectare zone pereți (nemodificat)
# =========================================
def detect_wall_zones(orig, mask):
    print("\n[STEP 6] Detectare zone pereți...")
    gray = (mask / 255).astype(np.float32)
    dens = cv2.GaussianBlur(gray, (51, 51), 0)
    norm = cv2.normalize(dens, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, dense_mask = cv2.threshold(norm, 60, 255, cv2.THRESH_BINARY)
    filled = dense_mask.copy()
    flood = np.zeros((gray.shape[0] + 2, gray.shape[1] + 2), np.uint8)
    cv2.floodFill(filled, flood, (0, 0), 0)
    walls = cv2.bitwise_not(filled)
    save_debug(walls, STEP_DIRS["walls"], "filled_unified.jpg")
    detect_clusters(walls, orig)

def _remove_red_overlays(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, (0, 60, 60), (10, 255, 255))
    m2 = cv2.inRange(hsv, (170, 60, 60), (179, 255, 255))
    mask = cv2.bitwise_or(m1, m2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    out = bgr.copy()
    out[mask > 0] = (255, 255, 255)
    return out, mask

def _largest_component_mask(binary_255, min_area_ratio=0.02, dilate_ratio=0.008):
    if binary_255.ndim == 3:
        binary_255 = cv2.cvtColor(binary_255, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(binary_255, 127, 255, cv2.THRESH_BINARY)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((5,5), np.uint8))
    num, labels, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
    if num <= 1:
        return bw
    h, w = bw.shape[:2]
    img_area = h * w
    best = None
    for i in range(1, num):
        a = stats[i, cv2.CC_STAT_AREA]
        if a >= min_area_ratio * img_area:
            if best is None or a > best[0]:
                best = (a, i)
    if best is None:
        keep = np.ones_like(bw) * 255
    else:
        keep = np.where(labels == best[1], 255, 0).astype(np.uint8)
    pad = max(3, int(dilate_ratio * max(h, w)))
    keep = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_RECT, (pad, pad)), iterations=1)
    return keep

def _suppress_thin_inside(bgr, keep_mask, thickness_px=2):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (thickness_px, thickness_px))
    thin = cv2.erode(edges, ker, iterations=1)
    thin = cv2.dilate(thin, ker, iterations=1)
    thin = cv2.bitwise_and(thin, keep_mask)
    out = bgr.copy()
    out[thin > 0] = (255, 255, 255)
    return out

# =========================================
# CLASIFICARE OpenAI + fallback (nemodificat)
# =========================================
OPENAI_PROMPT = (
    "You are an extremely strict architectural image classifier.\n"
    "Return exactly ONE lowercase label from this set: house_blueprint | site_blueprint | side_view | text_area.\n\n"
    "Definitions:\n"
    "- house_blueprint = HOUSE FLOOR PLAN (top-down 2D) with interior walls forming rooms, door/window symbols, dimension lines. "
    "Not an elevation, not a 3D render, not a site plan.\n"
    "- site_blueprint  = SITE/LOT plan: plot/property boundaries, setbacks, streets/road names, north arrow/compass rose, "
    "driveway/landscaping, terrain contours.\n"
    "- side_view       = exterior façade/elevation or 3D perspective view.\n"
    "- text_area       = page or crop dominated by paragraphs, tables, legends or mostly text.\n"
    "Output: house_blueprint OR site_blueprint OR side_view OR text_area."
)

def _prep_for_vlm(img_path, min_long_edge=1280):
    im = Image.open(img_path).convert("RGB")
    w, h = im.size
    long_edge = max(w, h)
    if long_edge < min_long_edge:
        scale = min_long_edge / float(long_edge)
        im = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=0.8, percent=110, threshold=2))
    return im

def _pil_to_base64(pil_img):
    import io
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")

def _extract_openai_text(resp_obj):
    try:
        if hasattr(resp_obj, "output_text"):
            return resp_obj.output_text
        if hasattr(resp_obj, "output") and hasattr(resp_obj.output, "text"):
            return resp_obj.output.text
    except Exception:
        pass
    try:
        if resp_obj and resp_obj.choices:
            return resp_obj.choices[0].message.get("content") or resp_obj.choices[0].message.content
    except Exception:
        pass
    return ""

# ------- Heuristici locale (fallback) -------
def _count_rect_rooms_and_lines(img_gray):
    g = cv2.GaussianBlur(img_gray, (3,3), 0)
    edges = cv2.Canny(g, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80, minLineLength=40, maxLineGap=8)
    angs = []
    if lines is not None:
        for l in lines:
            x1,y1, x2,y2 = l[0]
            ang = abs(math.degrees(math.atan2((y2-y1),(x2-x1)))) % 180.0
            angs.append(ang)
    angs = np.array(angs) if len(angs)>0 else np.array([])
    def is_ortho(a): return (min(abs(a-0), abs(a-180)) < 8) or (abs(a-90) < 8)
    def is_diag(a):  return (30 <= a <= 60) or (120 <= a <= 150)
    if angs.size>0:
        ortho = np.mean([1.0 if is_ortho(a) else 0.0 for a in angs])
        diag  = np.mean([1.0 if is_diag(a)  else 0.0 for a in angs])
    else:
        ortho, diag = 0.0, 0.0
    binv = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 21, 10)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(binv, 8)
    cc_small = 0
    for x in stats[1:]:
        a = x[cv2.CC_STAT_AREA]
        if 15 <= a <= 800:
            cc_small += 1
    cnts, _ = cv2.findContours(cv2.threshold(g,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1],
                               cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    rooms_like = 0
    h,w = img_gray.shape[:2]
    area_img = h*w
    for c in cnts:
        a = cv2.contourArea(c)
        if a < 0.0002*area_img or a > 0.25*area_img:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02*peri, True)
        if len(approx)==4 and cv2.isContourConvex(approx):
            rooms_like+=1
    return rooms_like, float(ortho), float(diag), int(cc_small)

def local_classify(img_path)->str:
    im = safe_imread(img_path)
    g  = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    rooms_like, ortho_ratio, diag_ratio, cc_small = _count_rect_rooms_and_lines(g)
    if DEBUG:
        print(f"🧪 LOCAL {Path(img_path).name}: rooms={rooms_like} ortho={ortho_ratio:.2f} diag={diag_ratio:.2f} textCC={cc_small}")
    if rooms_like <= 1 and cc_small >= 1800 and ortho_ratio <= 0.55:
        return "text_area"
    if rooms_like >= 5 and ortho_ratio >= 0.55 and diag_ratio <= 0.25:
        return "house_blueprint"
    if rooms_like <= 2 and diag_ratio >= 0.35:
        return "side_view"
    if rooms_like <= 2 and (cc_small >= 350 or ortho_ratio <= 0.45):
        return "site_blueprint"
    return "side_view"

def classify_with_openai():
    print("\n[STEP 8] Clasificare cu OpenAI (gpt-4o-mini) + fallback local + post-validare...")
    load_dotenv()
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("❌ Eroare: Lipsă OPENAI_API_KEY în .env")
        return
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        use_responses_api = hasattr(client, "responses")
    except Exception as e:
        print(f"⚠️ OpenAI SDK indisponibil ({e}). Folosim DOAR fallback local.")
        client = None
        use_responses_api = False

    crops_dir = os.path.join(OUTPUT_DIR, STEP_DIRS["clusters"]["crops"])
    bp_dir = os.path.join(OUTPUT_DIR, STEP_DIRS["classified"]["blueprints"])
    sp_dir = os.path.join(OUTPUT_DIR, STEP_DIRS["classified"]["siteplan"])
    sv_dir = os.path.join(OUTPUT_DIR, STEP_DIRS["classified"]["side_views"])
    tx_dir = os.path.join(OUTPUT_DIR, STEP_DIRS["classified"]["text"])
    for d in (bp_dir, sp_dir, sv_dir, tx_dir):
        os.makedirs(d, exist_ok=True)

    ALLOWED = {"house_blueprint", "site_blueprint", "side_view", "text_area"}

    def parse_label(txt: str) -> str:
        t = (txt or "").strip().lower()
        if t in ALLOWED:
            return t
        for w in ALLOWED:
            if w in t:
                return w
        return ""

    def classify_one_with_openai(img_path: str) -> str:
        if client is None:
            return ""
        try:
            pil_img = _prep_for_vlm(img_path)
            b64 = _pil_to_base64(pil_img)
            if use_responses_api:
                resp = client.responses.create(
                    model="gpt-4o-mini",
                    input=[{"role":"user","content":[
                        {"type":"input_text","text":OPENAI_PROMPT},
                        {"type":"input_image","image_url":f"data:image/png;base64,{b64}"}
                    ]}],
                    temperature=0.0,
                    max_output_tokens=64,
                )
                out = _extract_openai_text(resp)
                label = parse_label(out)
                if label: return label
                resp2 = client.responses.create(
                    model="gpt-4o-mini",
                    input=[{"role":"user","content":[
                        {"type":"input_text","text":"Return one label: house_blueprint | site_blueprint | side_view | text_area"},
                        {"type":"input_image","image_url":f"data:image/png;base64,{b64}"}
                    ]}],
                    temperature=0.0,
                    max_output_tokens=64,
                )
                return parse_label(_extract_openai_text(resp2))
            else:
                msg = [
                    {"role":"system","content":"You are a careful vision classifier."},
                    {"role":"user","content":[
                        {"type":"text","text":OPENAI_PROMPT},
                        {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}"}}
                    ]}
                ]
                resp = client.chat.completions.create(model="gpt-4o-mini", messages=msg, temperature=0.0, max_tokens=64)
                out = _extract_openai_text(resp)
                label = parse_label(out)
                if label: return label
                msg[1]["content"][0]["text"] = "Return one label: house_blueprint | site_blueprint | side_view | text_area"
                resp2 = client.chat.completions.create(model="gpt-4o-mini", messages=msg, temperature=0.0, max_tokens=64)
                return parse_label(_extract_openai_text(resp2))
        except Exception as e:
            if DEBUG: print(f"⚠️ OpenAI exception {Path(img_path).name}: {e}")
            return ""

    for img_file in sorted(os.listdir(crops_dir)):
        if not img_file.lower().endswith((".jpg",".jpeg",".png")):
            continue
        img_path = os.path.join(crops_dir, img_file)
        label = classify_one_with_openai(img_path) or local_classify(img_path)
        if label == "house_blueprint":
            shutil.copy(img_path, os.path.join(bp_dir, img_file)); print(f"🏗 house_blueprint: {img_file}")
        elif label == "site_blueprint":
            shutil.copy(img_path, os.path.join(sp_dir, img_file)); print(f"🗺 site_blueprint: {img_file}")
        elif label == "side_view":
            shutil.copy(img_path, os.path.join(sv_dir, img_file)); print(f"🏠 side_view: {img_file}")
        elif label == "text_area":
            shutil.copy(img_path, os.path.join(tx_dir, img_file)); print(f"📝 text_area: {img_file}")
        else:
            shutil.copy(img_path, os.path.join(tx_dir, img_file)); print(f"📝 text_area*(fallback): {img_file}")
    print("✅ Clasificare inițială finalizată!\n")

    print("[STEP 8B] Post-validare folder 'blueprints'...")
    moved = 0
    for img_file in sorted(os.listdir(bp_dir)):
        if not img_file.lower().endswith((".jpg",".jpeg",".png")): continue
        img_path = os.path.join(bp_dir, img_file)
        lbl = local_classify(img_path)
        if lbl in ("side_view","site_blueprint","text_area"):
            dst = os.path.join(
                sv_dir if lbl=="side_view" else (sp_dir if lbl=="site_blueprint" else tx_dir),
                img_file
            )
            shutil.move(img_path, dst); moved += 1
            print(f"↪️  mutat din blueprints în {Path(dst).parent.name}: {img_file}")
    print(f"✅ Post-validare terminată. Mutate din blueprints: {moved}\n")

# =========================================
# PIPELINE (segmentare)
# =========================================
def segment_rooms(path):
    print(f"\n🖼 Procesare imagine: {path}")
    img = safe_imread(path)
    no_text = remove_text_regions(img)
    gray = cv2.cvtColor(no_text, cv2.COLOR_BGR2GRAY)
    no_hatch = remove_hatched_areas(gray)
    outlines = detect_outlines(no_hatch)
    thick = filter_thick_lines(outlines)
    solid = solidify_walls(thick)
    detect_wall_zones(img, solid)
    print("🏁 Procesare completă!\n")

# =========================================
# ========  NOU: rafinare blueprint-uri  ========
# =========================================
def find_main_plan_bbox(walls_mask, min_area_ratio=0.02):
    if walls_mask.ndim == 3:
        walls_mask = cv2.cvtColor(walls_mask, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(walls_mask, 127, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel, iterations=1)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
    if num <= 1: return None
    h, w = bw.shape[:2]
    img_area = h * w
    candidates = []
    for i in range(1, num):
        x, y, ww, hh, a = stats[i]
        if a >= min_area_ratio * img_area:
            candidates.append((a, x, y, ww, hh))
    if not candidates:
        return (0, 0, w, h)
    candidates.sort(reverse=True, key=lambda t: t[0])
    _, x, y, ww, hh = candidates[0]
    return (x, y, x + ww, y + hh)

def keep_inside_outer_walls(orig_bgr, walls_mask_255, pad_ratio=0.004):
    if walls_mask_255.ndim == 3:
        walls_mask_255 = cv2.cvtColor(walls_mask_255, cv2.COLOR_BGR2GRAY)
    bw = cv2.morphologyEx(walls_mask_255, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=2)
    _, bw = cv2.threshold(bw, 127, 255, cv2.THRESH_BINARY)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
    if num <= 1:
        return orig_bgr.copy(), bw
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    cc = np.where(labels == idx, 255, 0).astype(np.uint8)
    cnts, _ = cv2.findContours(cc, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    keep = np.zeros_like(cc)
    cv2.drawContours(keep, cnts, -1, 255, thickness=-1)
    pad = max(1, int(pad_ratio * max(keep.shape)))
    keep = cv2.dilate(keep, np.ones((pad, pad), np.uint8), iterations=1)
    out = orig_bgr.copy()
    out[keep == 0] = (255, 255, 255)
    return out, keep

def refine_single_blueprint(img_path, idx=None):
    """
    Curățare periferie + ștergere exterior + crop ROI principal.
    Salvează:
      - debug: step9_bp_refined/debug
      - full curățat (opțional): step9_bp_refined/clean_full
      - crop final: step9_bp_refined/crops
    """
    base = Path(img_path).name
    tag = f"{idx:03d}_" if idx is not None else ""
    dbg_prefix = f"{tag}{Path(base).stem}"

    # 0) citire + (opțional) eliminare overlay roșu
    orig = safe_imread(img_path)
    save_debug(orig, STEP_DIRS["bp_refined"]["debug"], f"{dbg_prefix}_00_orig.jpg")
    orig_no_red, _ = _remove_red_overlays(orig)
    save_debug(orig_no_red, STEP_DIRS["bp_refined"]["debug"], f"{dbg_prefix}_00a_no_red.jpg")

    # 1) remove text
    no_text = remove_text_regions(orig_no_red)
    save_debug(no_text, STEP_DIRS["bp_refined"]["debug"], f"{dbg_prefix}_01_no_text.jpg")

    # 2) remove hatch (pe gray)
    gray = cv2.cvtColor(no_text, cv2.COLOR_BGR2GRAY)
    no_hatch = remove_hatched_areas(gray)
    save_debug(no_hatch, STEP_DIRS["bp_refined"]["debug"], f"{dbg_prefix}_02_no_hatch_gray.jpg")

    # 3) edges
    edges = detect_outlines(no_hatch)
    save_debug(edges, STEP_DIRS["bp_refined"]["debug"], f"{dbg_prefix}_03_edges.jpg")

    # 4) thick only
    thick = filter_thick_lines(edges)
    save_debug(thick, STEP_DIRS["bp_refined"]["debug"], f"{dbg_prefix}_04_thick.jpg")

    # 5) solidify
    solid = solidify_walls(thick)
    save_debug(solid, STEP_DIRS["bp_refined"]["debug"], f"{dbg_prefix}_05_solid.jpg")

    # 6) mask pereți
    gray_solid = (solid / 255).astype(np.float32)
    dens = cv2.GaussianBlur(gray_solid, (51, 51), 0)
    norm = cv2.normalize(dens, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, dense_mask = cv2.threshold(norm, 60, 255, cv2.THRESH_BINARY)
    filled = dense_mask.copy()
    flood = np.zeros((gray_solid.shape[0] + 2, gray_solid.shape[1] + 2), np.uint8)
    cv2.floodFill(filled, flood, (0, 0), 0)
    walls_mask = cv2.bitwise_not(filled)
    save_debug(walls_mask, STEP_DIRS["bp_refined"]["debug"], f"{dbg_prefix}_06_walls_mask.jpg")

    # 6.1) Șterge TOT exteriorul pereților
    inside_only, keep_mask = keep_inside_outer_walls(orig_no_red, walls_mask, pad_ratio=0.004)
    save_debug(inside_only, STEP_DIRS["bp_refined"]["debug"], f"{dbg_prefix}_07_inside_only.jpg")

    # (opțional) salvează pagina întreagă curățată
    if SAVE_CLEAN_FULL:
        clean_full_dir = os.path.join(OUTPUT_DIR, STEP_DIRS["bp_refined"]["root"], "clean_full")
        os.makedirs(clean_full_dir, exist_ok=True)
        cv2.imwrite(os.path.join(clean_full_dir, f"{dbg_prefix}_inside_full.jpg"), inside_only)

    # 7) BBox principal + pad
    bbox = find_main_plan_bbox(walls_mask, min_area_ratio=0.02)
    crops_dir = os.path.join(OUTPUT_DIR, STEP_DIRS["bp_refined"]["crops"])
    os.makedirs(crops_dir, exist_ok=True)

    if bbox is None:
        # fallback: tot inside_only, dar REDIMENSIONAT pentru pipeline
        crop = inside_only.copy()
        crop = resize_bgr_max_side(crop, MAX_PLAN_EXPORT_LONG_EDGE)
        out_path = os.path.join(crops_dir, f"{dbg_prefix}_crop.jpg")
        cv2.imwrite(out_path, crop)
        save_debug(crop, STEP_DIRS["bp_refined"]["crops"], f"{dbg_prefix}_crop.jpg")
        return out_path

    x1, y1, x2, y2 = bbox
    h, w = walls_mask.shape[:2]
    pad = int(0.015 * max(h, w))
    x1 = max(0, x1 - pad); y1 = max(0, y1 - pad)
    x2 = min(w, x2 + pad); y2 = min(h, y2 + pad)

    # 8) Crop din imaginea curățată
    crop = inside_only[y1:y2, x1:x2].copy()

    # (opțional) polish înăuntru: suprimă linii subțiri
    keep_crop = _largest_component_mask(walls_mask, min_area_ratio=0.02, dilate_ratio=0.010)[y1:y2, x1:x2]
    crop = _suppress_thin_inside(crop, keep_crop, thickness_px=2)

    # 🔻 NOU: micșorăm crop-ul final ca să nu fie uriaș pentru Roboflow / restul pipeline-ului
    crop = resize_bgr_max_side(crop, MAX_PLAN_EXPORT_LONG_EDGE)

    save_debug(crop, STEP_DIRS["bp_refined"]["crops"], f"{dbg_prefix}_crop.jpg")
    out_path = os.path.join(OUTPUT_DIR, STEP_DIRS["bp_refined"]["crops"], f"{dbg_prefix}_crop.jpg")
    return out_path

def refine_blueprints_after_classification():
    """
    După clasificare (și post-validare), ia fiecare imagine din step8_classified/blueprints,
    o rafinează (curățare periferie + auto-crop ROI plan) și salvează rezultatele în step9_bp_refined.
    Returnează lista cu căile fișierelor crop rezultate.
    """
    bp_dir   = os.path.join(OUTPUT_DIR, STEP_DIRS["classified"]["blueprints"])
    dbg_dir  = os.path.join(OUTPUT_DIR, STEP_DIRS["bp_refined"]["debug"])
    crops_dir= os.path.join(OUTPUT_DIR, STEP_DIRS["bp_refined"]["crops"])
    os.makedirs(dbg_dir, exist_ok=True)
    os.makedirs(crops_dir, exist_ok=True)
    if not os.path.isdir(bp_dir):
        print("ℹ️  Nu există folderul de blueprint-uri (poate n-a clasificat nimic drept house_blueprint).")
        return []
    imgs = [f for f in sorted(os.listdir(bp_dir)) if f.lower().endswith((".jpg",".jpeg",".png"))]
    if not imgs:
        print("ℹ️  Nu există imagini de rafinat în 'blueprints'.")
        return []
    print("\n[STEP 9] Rafinare blueprint-uri (curățare + auto-crop ROI)...")
    out_paths, ok, fail = [], 0, 0
    for i, fn in enumerate(imgs, 1):
        path = os.path.join(bp_dir, fn)
        try:
            out_path = refine_single_blueprint(path, idx=i)
            if out_path and os.path.isfile(out_path):
                out_paths.append(out_path); ok += 1
                print(f"✂️  Rafinare blueprint: {fn}")
            else:
                fail += 1; print(f"⚠️  Rafinarea nu a produs ieșire pentru: {fn}")
        except Exception as e:
            fail += 1; print(f"⚠️  Eroare la rafinare {fn}: {e}")
    print(f"✅ Rafinare blueprint-uri finalizată! Reușite: {ok}, eșecuri: {fail}\n")
    return out_paths

# =========================================
# === FRONTIER FLOOD ADAPTIVE (EXCLUSIVE) ===
# =========================================
# Flood în trepte pornind de pe frontiere, 100% adaptiv:
#  1) BLUE   – flood din margini (fundal), toleranță din statisticile marginilor
#  2) GREEN  – flood de pe frontiera BLUE, traversând doar delimitări foarte subțiri (percentilă joasă pe frontieră)
#  3) YELLOW – flood de pe frontiera (BLUE∪GREEN), traversând delimitări ceva mai groase (percentilă medie pe frontieră)
# Măștile sunt EXCLUSIVE (fără suprapuneri), apoi colorăm o singură dată.
#
# Intrare: OUTPUT_DIR/step8_classified/blueprints
# Ieșire:  OUTPUT_DIR/step9_frontier_bgy_exclusive

# (Valorile implicite vor fi suprascrise din frontier_main)
FF_INPUT_DIR  = os.path.join(OUTPUT_DIR, STEP_DIRS["classified"]["blueprints"])
FF_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "step9_frontier_bgy_exclusive")

def ff_imread(p: Path):
    arr = np.fromfile(str(p), np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def ff_odd(x: int) -> int:
    return x if x % 2 == 1 else x + 1

def ff_dynamic_seed_step(h, w):
    return max(6, int(min(h, w) / 64))

def ff_sample_border_stats(bgr):
    h, w = bgr.shape[:2]
    band = max(2, int(0.01 * min(h, w)))
    mask = np.zeros((h, w), np.uint8)
    mask[:band, :] = 1; mask[-band:, :] = 1
    mask[:, :band] = 1; mask[:, -band:] = 1
    border = bgr[mask > 0]
    if border.size == 0:
        return (200.0, 200.0, 200.0), (20.0, 20.0, 20.0)
    mean = np.median(border, axis=0)
    mad  = np.median(np.abs(border - mean), axis=0) + 1e-6
    std  = 1.4826 * mad
    return tuple(map(float, mean)), tuple(map(float, std))

def ff_detect_lines_mask(bgr):
    h, w = bgr.shape[:2]
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)

    k_open = max(1, min(int(0.0025 * min(h, w)), 5))
    k_edge_close = max(1, min(int(0.0035 * min(h, w)), 5))

    block = ff_odd(max(15, int(min(h, w) / 32)))
    C = max(5, int(block * 0.22))

    bw = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, block, C)
    if k_open > 1:
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((k_open, k_open), np.uint8))

    otsu_ret, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if not np.isfinite(otsu_ret) or otsu_ret <= 0:
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.sqrt(gx*gx + gy*gy)
        p50 = float(np.percentile(mag, 50))
        p90 = float(np.percentile(mag, 90))
        c_lo = int(max(5, 0.5 * p50))
        c_hi = int(max(30, 0.5 * p90))
    else:
        c_lo = int(max(5, 0.25 * otsu_ret))
        c_hi = int(max(30, 0.55 * max(50, otsu_ret)))

    edges = cv2.Canny(g, c_lo, c_hi)
    if k_edge_close > 1:
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((k_edge_close, k_edge_close), np.uint8))

    U = cv2.bitwise_or(bw, edges)
    U = cv2.morphologyEx(U, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    return U

def ff_thickness_dt(line_mask_255):
    return cv2.distanceTransform(line_mask_255, cv2.DIST_L2, 3)

def ff_flood_blue_from_border(bgr, mean_bg, std_bg):
    h, w = bgr.shape[:2]
    img = bgr.copy()
    ff_mask = np.zeros((h+2, w+2), np.uint8)
    flags = cv2.FLOODFILL_FIXED_RANGE
    tol = np.clip(1.5 * np.array(std_bg), 10, 36).astype(np.int32)
    lo = tuple(int(x) for x in tol)
    hi = tuple(int(x) for x in tol)
    step = ff_dynamic_seed_step(h, w)
    blue = (255, 0, 0)
    for x in range(0, w, step):
        for (sx, sy) in [(x, 0), (x, h-1)]:
            if ff_mask[sy+1, sx+1] != 0: continue
            try: cv2.floodFill(img, ff_mask, (sx, sy), blue, lo, hi, flags)
            except cv2.error: pass
    for y in range(0, h, step):
        for (sx, sy) in [(0, y), (w-1, y)]:
            if ff_mask[sy+1, sx+1] != 0: continue
            try: cv2.floodFill(img, ff_mask, (sx, sy), blue, lo, hi, flags)
            except cv2.error: pass
    return (ff_mask[1:-1, 1:-1] > 0).astype(np.uint8) * 255

def ff_make_frontier(mask255, ring_px=1):
    if mask255.ndim == 3:
        mask255 = cv2.cvtColor(mask255, cv2.COLOR_BGR2GRAY)
    ring_px = max(1, int(ring_px))
    dil = cv2.dilate(mask255, np.ones((2*ring_px+1, 2*ring_px+1), np.uint8), 1)
    return cv2.bitwise_and(dil, cv2.bitwise_not(mask255))

def ff_seeds_from_frontier(frontier255, max_seeds=20000):
    ys, xs = np.where(frontier255 > 0)
    if xs.size == 0:
        return []
    idx = np.arange(xs.size)
    if xs.size > max_seeds:
        step = int(np.ceil(xs.size / max_seeds))
        idx = idx[::step]
    return list(zip(xs[idx], ys[idx]))

def ff_flood_from_seeds_MASKONLY(h, w, obstacle255, seeds_xy):
    ff_mask = np.zeros((h+2, w+2), np.uint8)
    ff_mask[1:h+1, 1:w+1] = (obstacle255 > 0).astype(np.uint8)
    flags = cv2.FLOODFILL_MASK_ONLY | (255 << 8)
    tmp = np.zeros((h, w, 3), np.uint8)
    for (sx, sy) in seeds_xy:
        if 0 <= sx < w and 0 <= sy < h and ff_mask[sy+1, sx+1] == 0:
            try:
                cv2.floodFill(tmp, ff_mask, (sx, sy), 0, (0,0,0), (0,0,0), flags)
            except cv2.error:
                pass
    return (ff_mask[1:-1, 1:-1] == 255).astype(np.uint8) * 255

def ff_boundary_thickness_stats(frontier255, line_mask255, dt):
    if frontier255.ndim == 3:
        frontier255 = cv2.cvtColor(frontier255, cv2.COLOR_BGR2GRAY)
    f_on_lines = ((frontier255 > 0) & (line_mask255 > 0))
    vals = dt[f_on_lines] * 2.0
    if vals.size == 0:
        return None
    upper = np.percentile(vals, 99.7)
    vals = vals[(vals >= 0.5) & (vals <= upper)]
    return vals if vals.size > 0 else None

def ff_obstacle_from_threshold(line_mask255, dt, thickness_px):
    radius = max(1.0, 0.5 * float(thickness_px))
    return ((dt >= radius) & (line_mask255 > 0)).astype(np.uint8) * 255

def ff_process_one(p: Path):
    bgr = ff_imread(p)
    if bgr is None:
        print(f"⚠️ nu pot citi {p.name}")
        return
    h, w = bgr.shape[:2]
    base = p.stem

    L = ff_detect_lines_mask(bgr)
    dt = ff_thickness_dt(L)

    mean_bg, std_bg = ff_sample_border_stats(bgr)
    mask_blue = ff_flood_blue_from_border(bgr, mean_bg, std_bg)

    blue_front = ff_make_frontier(mask_blue, ring_px=max(1, int(0.002 * min(h, w))))
    blue_seeds = ff_seeds_from_frontier(blue_front)
    vals_blue = ff_boundary_thickness_stats(blue_front, L, dt)

    if vals_blue is None:
        mask_green = np.zeros((h, w), np.uint8)
    else:
        t_green = float(np.percentile(vals_blue, 20.0))
        obst_green = ff_obstacle_from_threshold(L, dt, t_green)
        fill_green = ff_flood_from_seeds_MASKONLY(h, w, obst_green, blue_seeds)
        mask_green = cv2.bitwise_and(fill_green, cv2.bitwise_not(mask_blue))

    green_union = cv2.bitwise_or(mask_blue, mask_green)
    green_front = ff_make_frontier(green_union, ring_px=max(1, int(0.002 * min(h, w))))
    green_seeds = ff_seeds_from_frontier(green_front)
    vals_green = ff_boundary_thickness_stats(green_front, L, dt)

    if vals_green is None:
        mask_yellow = np.zeros((h, w), np.uint8)
    else:
        t_yellow = float(np.percentile(vals_green, 40.0))
        if np.percentile(vals_green, 75) - np.percentile(vals_green, 25) < 1.0:
            t_yellow = max(t_yellow, float(np.percentile(vals_green, 50.0)))
        obst_yellow = ff_obstacle_from_threshold(L, dt, t_yellow)
        fill_yellow = ff_flood_from_seeds_MASKONLY(h, w, obst_yellow, green_seeds)
        prev_exclusive = green_union
        mask_yellow = cv2.bitwise_and(fill_yellow, cv2.bitwise_not(prev_exclusive))

    vis = bgr.copy()
    vis[mask_blue   > 0] = (255,   0,   0)
    vis[mask_green  > 0] = (  0, 255,   0)
    vis[mask_yellow > 0] = (  0, 255, 255)

    cv2.imwrite(os.path.join(FF_OUTPUT_DIR, f"{base}_lines.png"), L)
    cv2.imwrite(os.path.join(FF_OUTPUT_DIR, f"{base}_mask_blue.png"), mask_blue)
    cv2.imwrite(os.path.join(FF_OUTPUT_DIR, f"{base}_mask_green.png"), mask_green)
    cv2.imwrite(os.path.join(FF_OUTPUT_DIR, f"{base}_mask_yellow.png"), mask_yellow)
    cv2.imwrite(os.path.join(FF_OUTPUT_DIR, f"{base}_composite_bgy.png"), vis)

    def safe_pct(vs, q):
        try: return float(np.percentile(vs, q))
        except: return -1.0
    with open(os.path.join(FF_OUTPUT_DIR, f"{base}_stats.txt"), "w") as f:
        f.write("== frontier adaptive stats ==\n")
        if vals_blue is not None:
            f.write(f"BLUE frontier thickness px: P10={safe_pct(vals_blue,10):.2f} "
                    f"P20={safe_pct(vals_blue,20):.2f} P50={safe_pct(vals_blue,50):.2f}\n")
        else:
            f.write("BLUE frontier thickness: n/a\n")
        if vals_green is not None:
            f.write(f"GREEN frontier thickness px: P20={safe_pct(vals_green,20):.2f} "
                    f"P40={safe_pct(vals_green,40):.2f} P50={safe_pct(vals_green,50):.2f}\n")
        else:
            f.write("GREEN frontier thickness: n/a\n")

def frontier_main():
    """
    Rulează frontier flood pe blueprint-urile clasificate,
    în cadrul OUTPUT_DIR curent.
    """
    global FF_INPUT_DIR, FF_OUTPUT_DIR

    FF_INPUT_DIR  = os.path.join(OUTPUT_DIR, STEP_DIRS["classified"]["blueprints"])
    FF_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "step9_frontier_bgy_exclusive")
    os.makedirs(FF_OUTPUT_DIR, exist_ok=True)

    paths = [p for p in Path(FF_INPUT_DIR).glob("*")
             if p.suffix.lower() in {".png",".jpg",".jpeg",".tif",".tiff",".bmp"}]
    if not paths:
        print(f"ℹ️ Nu am imagini în {FF_INPUT_DIR}")
        return
    for i, p in enumerate(sorted(paths), 1):
        print(f"[{i}/{len(paths)}] {p.name}")
        ff_process_one(p)
    print("\n✅ Gata: frontier flood BLUE → GREEN (thin) → YELLOW (thicker), cu măști exclusive.")

# =========================================
# MAIN PIPELINE PENTRU UN INPUT
# =========================================
def process_input(p, output_dir=None):
    """
    p poate fi:
      - path către o imagine (png/jpg/pdf)
      - path către un folder cu imagini/pdf

    output_dir:
      - dacă e dat, rezultatele pentru acest job se duc în folderul respectiv
      - altfel, se folosește OUTPUT_DIR global (default 'test_out')

    return:
      - listă de path-uri PNG/JPG, fiecare reprezentând un plan (nivel) rafinat
    """
    # 1) pregătim OUTPUT_DIR pentru acest job
    reset_output_folders(output_dir)

    # 2) strângem fișierele de intrare
    if os.path.isdir(p):
        files = [
            str(f) for f in Path(p).glob("*")
            if f.suffix.lower() in [".png", ".jpg", ".jpeg", ".pdf"]
        ]
    else:
        files = [p]

    # 3) rulăm pipeline-ul pe fiecare fișier
    for f in files:
        ext = Path(f).suffix.lower()
        if ext == ".pdf":
            png_pages = convert_pdf_to_png(f, os.path.join(OUTPUT_DIR, "pdf_pages"))
            for pth in png_pages:
                segment_rooms(pth)
        else:
            segment_rooms(f)

    # 4) clasificare & rafinare blueprint-uri
    classify_with_openai()
    refined_crops = refine_blueprints_after_classification()  # list[str]

    # 5) (opțional) frontier flood pe blueprint-uri
    frontier_main()

    return refined_crops

# =========================================
# WORKFLOW: SEGMENTARE + PREȚ PE FIECARE PLAN
# =========================================
def run_pricing_workflow(input_paths, price_callback, output_dir_base="jobs_out"):
    """
    input_paths:
      - string / Path sau listă de path-uri (imagini + pdf-uri)
    price_callback:
      - funcție de forma: price_callback(plan_image_path) -> dict
        (aici tu integrezi workflow-ul tău de calcul preț pentru UN plan)

    return:
      - listă de dict-uri cu rezultate pe fiecare plan detectat
        [
          {
            "source_file": <fișierul original>,
            "plan_index": <index 1..N în fișierul respectiv>,
            "plan_image": <path crop plan>,
            "price": ...,
            "currency": ...,
            "extra": ...,
          },
          ...
        ]
    """
    if isinstance(input_paths, (str, Path)):
        input_paths = [str(input_paths)]
    else:
        input_paths = [str(p) for p in input_paths]

    results = []
    os.makedirs(output_dir_base, exist_ok=True)

    for upload_path in input_paths:
        job_id = uuid.uuid4().hex[:8]
        job_output_dir = os.path.join(output_dir_base, f"job_{job_id}")

        print(f"\n🚀 Job nou pentru '{upload_path}' în '{job_output_dir}'")

        # 1) segmentare + clasificare + crop per plan
        plan_paths = process_input(upload_path, output_dir=job_output_dir)

        # 2) calcul preț pentru fiecare plan detectat
        for idx, plan_path in enumerate(plan_paths, start=1):
            print(f"💰 Calcul preț pentru plan #{idx}: {plan_path}")
            price_info = price_callback(plan_path) or {}

            results.append({
                "source_file": upload_path,
                "plan_index": idx,
                "plan_image": plan_path,
                "price": price_info.get("price"),
                "currency": price_info.get("currency"),
                "extra": price_info,
            })

    return results

# =========================================
# EXEMPLE / TEST LOCAL
# =========================================
if __name__ == "__main__":
    # Exemplu simplu: doar segmentare + listare planuri
    plans = process_input(INPUT_PATH)  # folosește OUTPUT_DIR default sau schimbă INPUT_PATH
    print("Planuri rafinate găsite:")
    for p in plans:
        print("  -", p)

    # Exemplu: integrare cu un workflow de preț (dummy)
    def dummy_price_callback(plan_img):
        # Aici tu bagi workflow-ul REAL cu GPT / Vision / calcul lungimi etc.
        # Eu pun doar un placeholder.
        return {
            "price": 1234.5,
            "currency": "EUR",
            "note": f"Dummy price pentru {os.path.basename(plan_img)}"
        }

    results = run_pricing_workflow([INPUT_PATH], price_callback=dummy_price_callback)
    print("\nRezultate pricing per plan:")
    for r in results:
        print(f"- {os.path.basename(r['source_file'])} | plan #{r['plan_index']} "
              f"| {r['price']} {r['currency']} | img={r['plan_image']}")
