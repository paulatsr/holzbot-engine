# engine/ui_export.py
import os
import json
import shutil
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image
except Exception:
    Image = None  # fallback: copiere brută dacă nu e PIL

# integrare backend (evenimente + upload)
try:
    from net_bridge import post_event
except Exception:
    def post_event(*_a, **_kw):  # fallback inert
        return False

PROJECT_ROOT = Path(__file__).resolve().parent
UI_OUT_ROOT = PROJECT_ROOT / "ui_out"

# ======== FIX: RUN_DIR stabil și comun tuturor proceselor ========
# Preferăm UI_RUN_DIR sau RUN_ID din env; dacă lipsesc, generăm un timestamp local (dar stabil pe procesul curent).
_env_run = os.getenv("UI_RUN_DIR") or os.getenv("RUN_ID")
if _env_run:
    RUN_DIR = UI_OUT_ROOT / f"run_{_env_run}"
else:
    RUN_DIR = UI_OUT_ROOT / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
RUN_DIR.mkdir(parents=True, exist_ok=True)

# Folosim același RUN_STARTED_TS pentru toate procesele din run (dacă e în env).
try:
    RUN_STARTED_TS = float(os.getenv("RUN_STARTED_TS", ""))
except Exception:
    RUN_STARTED_TS = None
if RUN_STARTED_TS is None:
    RUN_STARTED_TS = datetime.now().timestamp()

def get_run_dir() -> Path:
    return RUN_DIR

# ---------------- helpers ----------------
def _under(child: Path, root: Path) -> bool:
    try:
        return child.resolve().is_relative_to(root.resolve())
    except AttributeError:
        cr, rr = str(child.resolve()), str(root.resolve())
        return cr == rr or cr.startswith(rr.rstrip("/") + "/")

def _stage_dir(stage: str) -> Path:
    d = RUN_DIR / stage
    d.mkdir(parents=True, exist_ok=True)
    return d

def _counter_path(stage: str) -> Path:
    return _stage_dir(stage) / ".counter"

def _read_counter(stage: str) -> int:
    cp = _counter_path(stage)
    if not cp.exists():
        cp.write_text("1", encoding="utf-8")  # _01 va fi primul vizual
        return 1
    try:
        return int(cp.read_text(encoding="utf-8").strip())
    except Exception:
        cp.write_text("1", encoding="utf-8")
        return 1

def _bump_counter(stage: str) -> int:
    n = _read_counter(stage)
    _counter_path(stage).write_text(str(n + 1), encoding="utf-8")
    return n

def _nn(n: int) -> str:
    return f"_{n:02d}"

def _copy_any(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)

def _save_image_as_png(src: Path, dst_png: Path):
    if Image is None:
        _copy_any(src, dst_png.with_suffix(src.suffix))
        return
    try:
        with Image.open(src) as im:
            im.save(dst_png, format="PNG")
    except Exception:
        _copy_any(src, dst_png.with_suffix(src.suffix))

def _is_recent(p: Path) -> bool:
    try:
        return p.stat().st_mtime >= RUN_STARTED_TS
    except Exception:
        return True

def _plan_suffix() -> str:
    """Mic utilitar pt. a marca evenimentele cu planul curent (ex. '(p01)')."""
    pid = os.getenv("PLAN_ID") or ""
    return f" ({pid})" if pid else ""

IMG_EXTS   = {".png", ".jpg", ".jpeg"}
JSON_EXTS  = {".json"}
ARRAY_EXTS = {".npy", ".npz"}

SEARCH_ROOTS = {
    "evaluate_plan":   [PROJECT_ROOT / "evaluate_plan", PROJECT_ROOT],
    "export_objects":  [PROJECT_ROOT / "export_objects"],
    "count_objects":   [PROJECT_ROOT / "count_objects"],
    "meters_pixel":    [PROJECT_ROOT / "meters_pixel"],
    "measure_openings":[PROJECT_ROOT / "measure_objects"],
    "exterior_doors":  [PROJECT_ROOT / "exterior_doors"],
    "perimeter":       [PROJECT_ROOT / "perimeter"],
    "area_walls":      [PROJECT_ROOT / "area"],
    "area_house":      [PROJECT_ROOT / "area"],
    "roof":            [PROJECT_ROOT / "roof"],
    "house_pricing":   [PROJECT_ROOT],
}

AUTO_PATTERNS = {
    "evaluate_plan":   ["plan_evaluation_gemini25.json", "**/*.json", "**/*.png", "**/*.jpg", "**/*.jpeg"],
    "export_objects":  ["exports/**/*.png", "**/*.png", "**/*.jpg", "**/*.json"],
    "count_objects":   ["output/**/*.png", "detections_all.json", "**/*.png", "**/*.jpg", "**/*.json"],
    "meters_pixel":    ["**/*.json", "**/*.png", "**/*.jpg"],
    "measure_openings":["**/*.json", "**/*.png", "**/*.jpg"],
    "exterior_doors":  ["**/*.json", "**/*.png", "**/*.jpg", "**/*.jpeg"],
    "perimeter":       ["**/*.json", "**/*.png", "**/*.jpg"],
    "area_walls":      ["**/*.json", "**/*.png", "**/*.jpg"],
    "area_house":      ["house_area_gemini.json", "**/*.json", "**/*.png", "**/*.jpg"],
    "roof":            ["**/*.json", "**/*.png", "**/*.jpg"],
    "house_pricing":   ["house_pricing*.json", "**/*.json", "**/*.png", "**/*.jpg"],
}

# —— reguli speciale:
EXCLUDE_BASENAMES = {
    "evaluate_plan": {"plan.jpg", "plan.jpeg", "plan.png"},
}

# limite de imagini per etapă (și eșantionare uniformă în autocolectare)
MAX_STAGE_IMAGES = {
    "export_objects": 5,
    "evaluate_plan": None,
}

# —— helper: decizie dacă permitem post_event pentru o etapă
def _can_post(stage: str) -> bool:
    """
    În mod implicit trimitem evenimente pentru toate etapele.
    Poți dezactiva house_pricing prin env: POST_HOUSE_PRICING=false
    """
    if stage == "house_pricing":
        return os.getenv("POST_HOUSE_PRICING", "true").lower() == "true"
    return True


def _collect_one(stage: str, p: Path, sd: Path, counters) -> bool:
    if not p.is_file() or not _is_recent(p):
        return False
    if _under(p, RUN_DIR):
        return False
    ex = EXCLUDE_BASENAMES.get(stage)
    if ex and p.name.lower() in ex:
        return False

    ext = p.suffix.lower()

    if ext in IMG_EXTS:
        max_imgs = MAX_STAGE_IMAGES.get(stage)
        next_idx = counters.get(stage)
        if next_idx is None:
            next_idx = _read_counter(stage)
        if max_imgs is not None and next_idx > max_imgs:
            return False

        idx = next_idx
        counters[stage] = idx + 1
        _counter_path(stage).write_text(str(idx + 1), encoding="utf-8")

        dst = sd / f"{_nn(idx)}.png"
        try:
            if p.resolve() == dst.resolve():
                return False
        except Exception:
            pass
        _save_image_as_png(p, dst)
        if _can_post(stage):
            try:
                post_event(f"[{stage}{_plan_suffix()}] imagine: {dst.name}", files=[dst])  # ← include planul
            except Exception:
                pass
        return True

    if ext in (JSON_EXTS | ARRAY_EXTS):
        dst = sd / p.name
        try:
            if p.resolve() == dst.resolve():
                return False
        except Exception:
            pass
        _copy_any(p, dst)
        if _can_post(stage):
            try:
                post_event(f"[{stage}{_plan_suffix()}] fișier: {dst.name}", files=[dst])  # ← include planul
            except Exception:
                pass
        return True

    return False

def _autocollect(stage: str):
    sd = _stage_dir(stage)
    roots = SEARCH_ROOTS.get(stage, [PROJECT_ROOT])
    patterns = AUTO_PATTERNS.get(stage, ["**/*"])
    counters = {}

    max_imgs = MAX_STAGE_IMAGES.get(stage)
    selected_images = []
    other_files = []

    def _is_candidate_image(p: Path) -> bool:
        if not p.is_file(): return False
        if _under(p, RUN_DIR): return False
        if not _is_recent(p): return False
        if p.suffix.lower() not in IMG_EXTS: return False
        ex = EXCLUDE_BASENAMES.get(stage)
        if ex and p.name.lower() in ex: return False
        return True

    for root in roots:
        for pat in patterns:
            for p in root.rglob(pat):
                if p.is_dir():
                    continue
                if _is_candidate_image(p):
                    selected_images.append(p)
                else:
                    if p.suffix.lower() in (JSON_EXTS | ARRAY_EXTS) and _is_recent(p) and not _under(p, RUN_DIR):
                        other_files.append(p)

    if max_imgs and len(selected_images) > max_imgs:
        total = len(selected_images)
        step = (total + max_imgs - 1) // max_imgs
        selected_images = [selected_images[i] for i in range(0, total, step)][:max_imgs]

    collected = 0
    for p in selected_images:
        if _collect_one(stage, p, sd, counters):
            collected += 1

    for p in other_files:
        _collect_one(stage, p, sd, counters)

    if collected == 0 and not other_files:
        for root in roots:
            for p in root.rglob("*"):
                if p.is_dir(): continue
                if _under(p, RUN_DIR): continue
                if not _is_recent(p): continue
                if p.suffix.lower() in (IMG_EXTS | JSON_EXTS | ARRAY_EXTS):
                    _collect_one(stage, p, sd, counters)

# ---------------- parsere de concluzie ----------------

def _try_read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _summarize_detections_list(data, max_list=5):
    lines = []
    counts = {}
    for d in data:
        t = str(d.get("type","unknown")).lower()
        counts[t] = counts.get(t, 0) + 1
    if counts:
        lines.append("- obiecte detectate:")
        for t,c in sorted(counts.items()):
            lines.append(f"  • {t}: {c} buc.")
    shown = 0
    for d in data:
        if shown >= max_list: break
        t = d.get("type","?")
        x1,y1,x2,y2 = (d.get("x1"),d.get("y1"),d.get("x2"),d.get("y2"))
        lines.append(f"  - {t} la (x1={x1}, y1={y1}, x2={x2}, y2={y2})")
        shown += 1
    return lines

def _conclusion_for_stage(stage: str, sd: Path) -> str:
    json_files = sorted(sd.glob("*.json"))
    lines = [f"# Concluzie {stage}", ""]
    wrote_something = False
    by_name = {jf.name: jf for jf in json_files}

    if stage == "evaluate_plan":
        p = by_name.get("plan_evaluation_gemini25.json") or (json_files[0] if json_files else None)
        if p:
            data = _try_read_json(p)
            if isinstance(data, dict):
                pq = data.get("plan_quality")
                de = data.get("detected_elements")
                ex = data.get("explanation")
                if pq: lines.append(f"- plan_quality: {pq}"); wrote_something = True
                if de: lines.append(f"- detected_elements: {', '.join(map(str,de))}"); wrote_something = True
                if ex: lines.append(f"- {ex}"); wrote_something = True

    elif stage in {"export_objects", "count_objects"}:
        cand = by_name.get("detections_all.json")
        if cand:
            data = _try_read_json(cand)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                lines += _summarize_detections_list(data, max_list=8)
                wrote_something = True
        if not wrote_something:
            for jf in json_files:
                data = _try_read_json(jf)
                if isinstance(data, list) and data and isinstance(data[0], dict) and "type" in data[0]:
                    lines += _summarize_detections_list(data, max_list=5)
                    wrote_something = True
                    break

    elif stage == "meters_pixel":
        for jf in json_files:
            data = _try_read_json(jf)
            if isinstance(data, dict):
                mpp = data.get("meters_per_pixel") or data.get("m_per_px")
                if mpp:
                    lines.append(f"- scara estimată: {mpp} m/pixel")
                    wrote_something = True
                    break

    elif stage == "measure_openings":
        for jf in json_files:
            data = _try_read_json(jf)
            if isinstance(data, dict) and "openings" in data and isinstance(data["openings"], list):
                lines.append(f"- deschideri măsurate: {len(data['openings'])} buc.")
                wrote_something = True
                break

    elif stage == "exterior_doors":
        for jf in json_files:
            data = _try_read_json(jf)
            if isinstance(data, dict) and "num_exterior_doors" in data:
                lines.append(f"- uși exterioare detectate: {data['num_exterior_doors']}")
                wrote_something = True
                break

    elif stage in {"perimeter", "area_walls"}:
        for jf in json_files:
            data = _try_read_json(jf)
            if isinstance(data, dict) and "estimations" in data:
                avg = data["estimations"].get("average_result")
                if avg:
                    lines.append(f"- pereți interiori (medie): {avg.get('interior_meters')} m")
                    lines.append(f"- pereți exteriori (medie): {avg.get('exterior_meters')} m")
                    wrote_something = True
                    break
            if isinstance(data, dict) and "totals" in data:
                for k,v in data["totals"].items():
                    lines.append(f"- {k}: {v}")
                    wrote_something = True
                break

    elif stage == "area_house":
        p = by_name.get("house_area_gemini.json") or (json_files[0] if json_files else None)
        if p:
            data = _try_read_json(p)
            if isinstance(data, dict):
                se = data.get("surface_estimation", {})
                fa = se.get("final_area_m2")
                if fa is not None:
                    lines.append(f"- suprafață finală estimată: {fa} m²")
                    wrote_something = True
                ex = data.get("explanation") or se.get("explanation")
                if ex:
                    lines.append(f"- {ex}")
                    wrote_something = True

    elif stage == "roof":
        for jf in json_files:
            data = _try_read_json(jf)
            if isinstance(data, dict) and "roof_final_total_eur" in data:
                total = data["roof_final_total_eur"]
                rtype = (data.get("inputs") or {}).get("roof_type", {}).get("name_de")
                if rtype:
                    lines.append(f"- tip acoperiș: {rtype}")
                lines.append(f"- cost total acoperiș: {total} EUR")
                wrote_something = True
                break

    elif stage == "house_pricing":
        for jf in json_files:
            data = _try_read_json(jf)
            if isinstance(data, dict) and "total_price_eur" in data:
                lines.append(f"- preț total casă: {data['total_price_eur']} EUR")
                wrote_something = True
                break

    if not wrote_something and json_files:
        for jf in json_files[:3]:
            data = _try_read_json(jf)
            if isinstance(data, dict):
                keys = list(data.keys())[:6]
                lines.append(f"- {jf.name}: chei={', '.join(keys)}")
                wrote_something = True
            elif isinstance(data, list):
                lines.append(f"- {jf.name}: listă cu {len(data)} elemente")
                wrote_something = True

    if not wrote_something:
        lines.append("(Nu am găsit JSON-uri relevante sau câmpuri recunoscute.)")

    return "\n".join(lines) + "\n"

# ---------------- API public ----------------

def begin_stage(stage: str, title: str, plan_hint: str):
    sd = _stage_dir(stage)
    _counter_path(stage).write_text("1", encoding="utf-8")
    intro = sd / "_00.txt"
    intro.write_text(f"# {title}\n\n{plan_hint.strip()}\n", encoding="utf-8")
    if _can_post(stage):
        try:
            post_event(f"[{stage}] {sd.name} — start", files=[intro])
        except Exception:
            pass

def finalize_stage(stage: str):
    """
    FINALIZE la fiecare plan:
      - autocollect + trimite evenimente per plan (cu marker PLAN_ID)
      - scrie _99.txt doar pentru ultimul plan
    """
    _autocollect(stage)
    
    try:
        pi = int(os.getenv("PLAN_INDEX", "0"))
        pc = int(os.getenv("PLAN_COUNT", "1"))
        plan_id = os.getenv("PLAN_ID", f"p{pi:02d}")
    except Exception:
        pi, pc = 0, 1
        plan_id = ""

    # ✅ Trimite evenimente pentru FIECARE plan (nu doar ultimul)
    sd = _stage_dir(stage)
    
    # Scrie concluzia doar pentru ultimul plan
    if pc <= 1 or (pi and pi >= pc):
        concl = sd / "_99.txt"
        content = _conclusion_for_stage(stage, sd)
        concl.write_text(content, encoding="utf-8")
        if _can_post(stage):
            try:
                post_event(f"[{stage}] Concluzie", files=[concl])
            except Exception:
                pass

def record_image(src_path, stage: str, **_ignore):
    sd = _stage_dir(stage)
    plan_id = os.getenv("PLAN_ID", "")
    suffix = f"_{plan_id}" if plan_id else ""
    
    max_imgs = MAX_STAGE_IMAGES.get(stage)
    next_idx = _read_counter(stage)
    if max_imgs is not None and next_idx > max_imgs:
        return
    
    idx = _bump_counter(stage)
    dst = sd / f"{_nn(idx)}{suffix}.png"
    _save_image_as_png(Path(src_path), dst)
    
    if _can_post(stage):
        try:
            post_event(f"[{stage}{_plan_suffix()}] imagine: {dst.name}", files=[dst])
        except Exception:
            pass

def record_json(src_path, stage: str, **_ignore):
    sd = _stage_dir(stage)
    plan_id = os.getenv("PLAN_ID", "")
    src = Path(src_path)
    
    # Adaugă suffix pentru multi-plan
    stem = src.stem
    if plan_id:
        stem = f"{stem}_{plan_id}"
    dst = sd / f"{stem}{src.suffix}"
    
    _copy_any(src, dst)
    if _can_post(stage):
        try:
            post_event(f"[{stage}{_plan_suffix()}] JSON: {dst.name}", files=[dst])
        except Exception:
            pass

def record_file(src_path, stage: str, **_ignore):
    sd = _stage_dir(stage)
    src = Path(src_path)
    dst = sd / src.name
    _copy_any(src, dst)
    if _can_post(stage):
        try:
            post_event(f"[{stage}{_plan_suffix()}] fișier: {dst.name}", files=[dst])  # ← include planul
        except Exception:
            pass

def record_array(src_path, stage: str, **_ignore):
    record_file(src_path, stage=stage)

def record_text(text: str, stage: str, filename: str = "log.txt", append: bool = True, **_ignore):
    sd = _stage_dir(stage)
    fp = sd / filename
    mode = "a" if append and fp.exists() else "w"
    with open(fp, mode, encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    if _can_post(stage) and not append:
        try:
            post_event(f"[{stage}{_plan_suffix()}] {text[:140]}", files=[fp])  # ← include planul
        except Exception:
            pass
