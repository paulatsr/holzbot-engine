# frontier_flood_adaptive_exclusive.py
# Flood în trepte pornind de pe frontiere, 100% adaptiv:
#  1) BLUE   – flood din margini (fundal), toleranță din statisticile marginilor
#  2) GREEN  – flood de pe frontiera BLUE, traversând doar delimitări foarte subțiri (percentilă joasă pe frontieră)
#  3) YELLOW – flood de pe frontiera (BLUE∪GREEN), traversând delimitări ceva mai groase (percentilă medie pe frontieră)
# Măștile sunt EXCLUSIVE (fără suprapuneri), apoi colorăm o singură dată.
#
# Intrare: test10_out/step8_classified/blueprints
# Ieșire:  test10_out/step9_frontier_bgy_exclusive

import os
from pathlib import Path
import cv2
import numpy as np

INPUT_DIR  = "test3_out/step8_classified/side_views"
OUTPUT_DIR = "test3_out/step9_frontier_bgy_exclusive"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------- Utils generale ----------------

def imread(p: Path):
    arr = np.fromfile(str(p), np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def odd(x: int) -> int:
    return x if x % 2 == 1 else x + 1

def dynamic_seed_step(h, w):
    # densitate seeds pe margini proporțională cu rezoluția
    return max(6, int(min(h, w) / 64))

def sample_border_stats(bgr):
    """Culoarea medie + variabilitatea fundalului din margini (pentru toleranța BLUE)."""
    h, w = bgr.shape[:2]
    band = max(2, int(0.01 * min(h, w)))  # 1% din latura minimă
    mask = np.zeros((h, w), np.uint8)
    mask[:band, :] = 1; mask[-band:, :] = 1
    mask[:, :band] = 1; mask[:, -band:] = 1
    border = bgr[mask > 0]
    if border.size == 0:
        return (200.0, 200.0, 200.0), (20.0, 20.0, 20.0)
    mean = np.median(border, axis=0)
    mad  = np.median(np.abs(border - mean), axis=0) + 1e-6
    std  = 1.4826 * mad  # ~std
    return tuple(map(float, mean)), tuple(map(float, std))

# ---------------- Linii + grosimi ----------------

def detect_lines_mask(bgr):
    """
    Masca 0/255 a liniilor (fără solidify), adaptată rezoluției.
    """
    h, w = bgr.shape[:2]
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)

    # morfologie adaptivă
    k_open = max(1, min(int(0.0025 * min(h, w)), 5))
    k_edge_close = max(1, min(int(0.0035 * min(h, w)), 5))

    block = odd(max(15, int(min(h, w) / 32)))
    C = max(5, int(block * 0.22))

    bw = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, block, C)
    if k_open > 1:
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((k_open, k_open), np.uint8))

    # Canny cu praguri din Otsu (scalar) + fallback
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

def thickness_dt(line_mask_255):
    """
    Distance transform pe masca 0/255 a liniilor.
    Grosime(px) ≈ 2 * DT (DT în pixeli).
    """
    return cv2.distanceTransform(line_mask_255, cv2.DIST_L2, 3)

# ---------------- Flood-uri ----------------

def flood_blue_from_border(bgr, mean_bg, std_bg):
    """
    Flood (BGR) FIXED_RANGE din margini → masca BLUE (0/255).
    Toleranța e ~1.5*std_bg per canal, limitată [10..36].
    """
    h, w = bgr.shape[:2]
    img = bgr.copy()
    ff_mask = np.zeros((h+2, w+2), np.uint8)
    flags = cv2.FLOODFILL_FIXED_RANGE

    tol = np.clip(1.5 * np.array(std_bg), 10, 36).astype(np.int32)
    lo = tuple(int(x) for x in tol)
    hi = tuple(int(x) for x in tol)

    step = dynamic_seed_step(h, w)
    blue = (255, 0, 0)

    # sus/jos
    for x in range(0, w, step):
        for (sx, sy) in [(x, 0), (x, h-1)]:
            if ff_mask[sy+1, sx+1] != 0: continue
            try: cv2.floodFill(img, ff_mask, (sx, sy), blue, lo, hi, flags)
            except cv2.error: pass
    # st/dr
    for y in range(0, h, step):
        for (sx, sy) in [(0, y), (w-1, y)]:
            if ff_mask[sy+1, sx+1] != 0: continue
            try: cv2.floodFill(img, ff_mask, (sx, sy), blue, lo, hi, flags)
            except cv2.error: pass

    return (ff_mask[1:-1, 1:-1] > 0).astype(np.uint8) * 255

def make_frontier(mask255, ring_px=1):
    """
    Frontiera (= inel subțire) a unei regiuni binare 0/255.
    """
    if mask255.ndim == 3:
        mask255 = cv2.cvtColor(mask255, cv2.COLOR_BGR2GRAY)
    ring_px = max(1, int(ring_px))
    dil = cv2.dilate(mask255, np.ones((2*ring_px+1, 2*ring_px+1), np.uint8), 1)
    return cv2.bitwise_and(dil, cv2.bitwise_not(mask255))

def seeds_from_frontier(frontier255, max_seeds=20000):
    """
    Eșantionează coordonate (x,y) de pe frontieră ca seeds pentru flood.
    """
    ys, xs = np.where(frontier255 > 0)
    if xs.size == 0:
        return []
    idx = np.arange(xs.size)
    if xs.size > max_seeds:
        step = int(np.ceil(xs.size / max_seeds))
        idx = idx[::step]
    return list(zip(xs[idx], ys[idx]))

def flood_from_seeds_MASKONLY(h, w, obstacle255, seeds_xy):
    """
    Flood pe mască (MASK_ONLY) cu seeds custom (nu din margini).
    obstacle255>0 blochează. Returnează masca flood-uită (0/255).
    """
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

# ---------------- Praguri ADAPTIVE din frontieră ----------------

def boundary_thickness_stats(frontier255, line_mask255, dt):
    """
    Grosimi (2*dt) DOAR unde frontiera atinge linii. Returnează vector grosimi px sau None.
    """
    if frontier255.ndim == 3:
        frontier255 = cv2.cvtColor(frontier255, cv2.COLOR_BGR2GRAY)
    f_on_lines = ((frontier255 > 0) & (line_mask255 > 0))
    vals = dt[f_on_lines] * 2.0
    if vals.size == 0:
        return None
    upper = np.percentile(vals, 99.7)
    vals = vals[(vals >= 0.5) & (vals <= upper)]
    return vals if vals.size > 0 else None

def obstacle_from_threshold(line_mask255, dt, thickness_px):
    """
    Mască obstacole: pixeli de linie cu grosime >= thickness_px → 255.
    """
    radius = max(1.0, 0.5 * float(thickness_px))
    return ((dt >= radius) & (line_mask255 > 0)).astype(np.uint8) * 255

# ---------------- Pipeline pe imagine ----------------

def process_one(p: Path):
    bgr = imread(p)
    if bgr is None:
        print(f"⚠️ nu pot citi {p.name}")
        return
    h, w = bgr.shape[:2]
    base = p.stem

    # 1) linii + DT (grosimi)
    L = detect_lines_mask(bgr)
    dt = thickness_dt(L)

    # 2) BLUE – flood din margini (fundal)
    mean_bg, std_bg = sample_border_stats(bgr)
    mask_blue = flood_blue_from_border(bgr, mean_bg, std_bg)

    # 3) GREEN – seeds = frontiera BLUE; prag = percentilă joasă a grosimii pe frontieră (P20)
    blue_front = make_frontier(mask_blue, ring_px=max(1, int(0.002 * min(h, w))))
    blue_seeds = seeds_from_frontier(blue_front)
    vals_blue = boundary_thickness_stats(blue_front, L, dt)

    if vals_blue is None:
        mask_green = np.zeros((h, w), np.uint8)
    else:
        t_green = float(np.percentile(vals_blue, 20.0))  # „cele mai subțiri delimitări”
        obst_green = obstacle_from_threshold(L, dt, t_green)
        fill_green = flood_from_seeds_MASKONLY(h, w, obst_green, blue_seeds)
        # EXCLUSIV față de BLUE
        mask_green = cv2.bitwise_and(fill_green, cv2.bitwise_not(mask_blue))

    # 4) YELLOW – seeds = frontiera(BLUE∪GREEN); prag = percentilă medie (P40) pe noua frontieră
    green_union = cv2.bitwise_or(mask_blue, mask_green)
    green_front = make_frontier(green_union, ring_px=max(1, int(0.002 * min(h, w))))
    green_seeds = seeds_from_frontier(green_front)
    vals_green = boundary_thickness_stats(green_front, L, dt)

    if vals_green is None:
        mask_yellow = np.zeros((h, w), np.uint8)
    else:
        t_yellow = float(np.percentile(vals_green, 40.0))
        # dacă frontiera are distribuție foarte strânsă, ridicăm la mediană
        if np.percentile(vals_green, 75) - np.percentile(vals_green, 25) < 1.0:
            t_yellow = max(t_yellow, float(np.percentile(vals_green, 50.0)))
        obst_yellow = obstacle_from_threshold(L, dt, t_yellow)
        fill_yellow = flood_from_seeds_MASKONLY(h, w, obst_yellow, green_seeds)
        # EXCLUSIV față de (BLUE ∪ GREEN)
        prev_exclusive = green_union
        mask_yellow = cv2.bitwise_and(fill_yellow, cv2.bitwise_not(prev_exclusive))

    # --- sanity: fără suprapuneri
    if (cv2.countNonZero(cv2.bitwise_and(mask_green, mask_blue)) or
        cv2.countNonZero(cv2.bitwise_and(mask_yellow, mask_blue)) or
        cv2.countNonZero(cv2.bitwise_and(mask_yellow, mask_green))):
        print(f"⚠️ overlap detectat în {p.name} (a fost corectat cu măști exclusive)")

    # 5) Vizualizare (o singură trecere, nu suprascriem)
    vis = bgr.copy()
    vis[mask_blue   > 0] = (255,   0,   0)   # BLUE
    vis[mask_green  > 0] = (  0, 255,   0)   # GREEN
    vis[mask_yellow > 0] = (  0, 255, 255)   # YELLOW

    # Salvări
    cv2.imwrite(os.path.join(OUTPUT_DIR, f"{base}_lines.png"), L)
    cv2.imwrite(os.path.join(OUTPUT_DIR, f"{base}_mask_blue.png"), mask_blue)
    cv2.imwrite(os.path.join(OUTPUT_DIR, f"{base}_mask_green.png"), mask_green)
    cv2.imwrite(os.path.join(OUTPUT_DIR, f"{base}_mask_yellow.png"), mask_yellow)
    cv2.imwrite(os.path.join(OUTPUT_DIR, f"{base}_composite_bgy.png"), vis)

    # Statistici utile
    def safe_pct(vs, q):
        try: return float(np.percentile(vs, q))
        except: return -1.0
    with open(os.path.join(OUTPUT_DIR, f"{base}_stats.txt"), "w") as f:
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

def main():
    paths = [p for p in Path(INPUT_DIR).glob("*")
             if p.suffix.lower() in {".png",".jpg",".jpeg",".tif",".tiff",".bmp"}]
    if not paths:
        print(f"ℹ️ Nu am imagini în {INPUT_DIR}")
        return
    for i, p in enumerate(sorted(paths), 1):
        print(f"[{i}/{len(paths)}] {p.name}")
        process_one(p)
    print("\n✅ Gata: frontier flood BLUE → GREEN (thin) → YELLOW (thicker), cu măști exclusive.")

if __name__ == "__main__":
    main()
