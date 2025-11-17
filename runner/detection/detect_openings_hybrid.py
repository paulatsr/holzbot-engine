# runner/detection/detect_openings_hybrid.py
import google.generativeai as genai
import cv2
import numpy as np
from pathlib import Path
import os
import time
import shutil
import json
import requests

from runner.ui_export import record_image, record_json

# ==============================================
# CONFIGURARE
# ==============================================
API_KEY_ROBOFLOW = os.getenv("ROBOFLOW_API_KEY")
if not API_KEY_ROBOFLOW:
    raise RuntimeError("ROBOFLOW_API_KEY missing in environment")

WORKSPACE = os.getenv("ROBOFLOW_WORKSPACE") or "blueprint-recognition"
PROJECT_NAME = os.getenv("ROBOFLOW_PROJECT") or "house-plan-uwkew"
VERSION = int(os.getenv("ROBOFLOW_VERSION") or "5")

PLAN_PATH = "plan.jpg"
CONF_THRESHOLD = 0.3
OVERLAP = 30
TEMPLATE_SIMILARITY = 0.45

DOOR_TEMPLATES = Path("export_objects/exports/door")
DOUBLE_DOOR_TEMPLATES = Path("export_objects/exports/double_door")
WINDOW_TEMPLATES = Path("export_objects/exports/window")
DOUBLE_WINDOW_TEMPLATES = Path("export_objects/exports/double_window")
TEMP_DIR = Path("count_objects/temp")
OUT_PATH = Path("count_objects/plan_detected_all_hybrid.jpg")
DETECTIONS_JSON = Path("count_objects/detections_all.json")

# ==============================================
# CULORI (BGR)
# ==============================================
COLORS = {
    "door": {"template": (0, 165, 255), "gemini": (0, 255, 255)},
    "double-door": {"template": (255, 0, 200), "gemini": (255, 150, 255)},
    "window": {"template": (255, 0, 0), "gemini": (255, 150, 150)},
    "double-window": {"template": (0, 255, 0), "gemini": (144, 238, 144)},
}

# ==============================================
# INIT GEMINI
# ==============================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing in environment")
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")


def preprocess_for_ai(img_path, size=128):
    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Imagine invalidă: {img_path}")
    img = cv2.equalizeHist(img)
    img = cv2.convertScaleAbs(img, alpha=1.4, beta=15)
    if np.mean(img > 200) < 0.3:
        img = cv2.bitwise_not(img)
    img = cv2.resize(img, (size, size))
    _, img = cv2.threshold(img, 180, 255, cv2.THRESH_BINARY)
    processed_path = str(TEMP_DIR / f"proc_{Path(img_path).name}")
    cv2.imwrite(processed_path, img)
    return processed_path


def ask_gemini(template_path, candidate_path, label):
    """Verifică dacă imaginea candidat e același tip ca template-ul dar rotit (înclinat)."""
    try:
        prompt = (
            f"Ești expert în interpretarea planurilor arhitecturale 2D. "
            f"Prima imagine arată un {label} standard, drept (neînclinat). "
            f"A doua imagine este un extras dintr-un plan tehnic. "
            f"Determină dacă a doua imagine reprezintă același tip de obiect, "
            f"dar rotit față de orizontală/verticală (ex. 30–60°). "
            f"Răspunde strict 'DA' sau 'NU'."
        )
        temp_proc = preprocess_for_ai(template_path)
        cand_proc = preprocess_for_ai(candidate_path)
        response = gemini_model.generate_content(
            [
                prompt,
                {"mime_type": "image/jpeg", "data": open(temp_proc, "rb").read()},
                {"mime_type": "image/jpeg", "data": open(cand_proc, "rb").read()},
            ]
        )
        text = (response.text or "").strip().upper()
        print(f"   [Gemini] Răspuns brut: {text}")
        return "DA" in text
    except Exception as e:
        print(f"[Gemini ERR] {e}")
        return False


def load_templates(root_dir):
    templates = []
    for f in root_dir.glob("*.png"):
        img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        base = cv2.equalizeHist(img)
        for ang in [0, 90, 180, 270]:
            M = cv2.getRotationMatrix2D((img.shape[1] / 2, img.shape[0] / 2), ang, 1.0)
            rotated = cv2.warpAffine(
                base, M, (img.shape[1], img.shape[0]), borderValue=255
            )
            templates.append({"name": f.name, "image": rotated})
    return templates


def match_with_rotation(crop, templates, scales):
    best_sim = 0
    for crop_angle in [0, 45, 90, 135, 180, 225, 270, 315]:
        h, w = crop.shape
        M = cv2.getRotationMatrix2D((w / 2, h / 2), crop_angle, 1.0)
        cos, sin = abs(M[0, 0]), abs(M[0, 1])
        new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
        M[0, 2] += (new_w / 2) - (w / 2)
        M[1, 2] += (new_h / 2) - (h / 2)
        rotated_crop = cv2.warpAffine(crop, M, (new_w, new_h), borderValue=255)
        for t in templates:
            for s in scales:
                try:
                    resized = cv2.resize(
                        rotated_crop,
                        (int(t["image"].shape[1] * s), int(t["image"].shape[0] * s)),
                    )
                    sim = cv2.minMaxLoc(
                        cv2.matchTemplate(resized, t["image"], cv2.TM_CCOEFF_NORMED)
                    )[1]
                    best_sim = max(best_sim, sim)
                except Exception:
                    continue
    return best_sim


def overlap(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = min(ax2, bx2) - max(ax1, bx1)
    dy = min(ay2, by2) - max(ay1, by1)
    if dx <= 0 or dy <= 0:
        return 0
    area_overlap = dx * dy
    area_a = (ax2 - ax1) * (ay2 - ay1)
    return area_overlap / area_a


def infer_roboflow(image_path: str, max_retries: int = 5, timeout: int = 60) -> dict:
    """Încearcă infer.roboflow.com, apoi detect.roboflow.com, returnează dict cu cheia 'predictions'."""
    # 1) infer.roboflow.com
    infer_url = f"https://infer.roboflow.com/{WORKSPACE}/{PROJECT_NAME}/{VERSION}"
    headers = {
        "Authorization": f"Key {API_KEY_ROBOFLOW}",
        "Accept": "application/json",
        "Content-Type": "image/jpeg",
    }
    img_bytes = open(image_path, "rb").read()
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(infer_url, headers=headers, data=img_bytes, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and "predictions" in data:
                    return data
                return {"predictions": data.get("predictions", [])}
            elif r.status_code in (401, 403, 404, 405):
                print(
                    f"[INFO] infer.roboflow.com returned {r.status_code}; încerc detect.roboflow.com"
                )
                break
            else:
                print(f"[WARN] infer {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"[ERR] infer exception (try {attempt}/{max_retries}): {e}")
        time.sleep(1.2)

    # 2) detect.roboflow.com
    detect_url = f"https://detect.roboflow.com/{PROJECT_NAME}/{VERSION}"
    params = {"api_key": API_KEY_ROBOFLOW}
    files = {"file": (Path(image_path).name, open(image_path, "rb"), "image/jpeg")}
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(detect_url, params=params, files=files, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                return {"predictions": data.get("predictions", [])}
            else:
                print(f"[WARN] detect {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"[ERR] detect exception (try {attempt}/{max_retries}): {e}")
        time.sleep(1.2)

    raise RuntimeError("Nu am reușit să obțin predicții de la Roboflow (infer/detect).")


def _norm_class(c: str) -> str:
    return (c or "").lower().replace("_", "-").strip()


def main_single_plan():
    # CURĂȚARE TEMP
    if TEMP_DIR.exists():
        print(f"[CLEANUP] Șterg conținutul folderului temporar: {TEMP_DIR}")
        for item in TEMP_DIR.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as e:
                print(f"[WARN] Nu s-a putut șterge {item}: {e}")
    else:
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Folderul {TEMP_DIR} a fost creat.")

    # RUN YOLO
    print(f"[STEP] Rulez Hosted Inference pe {PLAN_PATH} ...")
    t0 = time.time()
    rf_result = infer_roboflow(PLAN_PATH)
    preds = rf_result.get("predictions", []) or []
    print(f"[DONE] {len(preds)} detecții YOLO în {time.time() - t0:.2f}s")

    img = cv2.imread(PLAN_PATH)
    if img is None:
        raise RuntimeError(f"Nu pot citi imaginea: {PLAN_PATH}")
    gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    scales = [0.9, 1.0, 1.1]

    EXPORTS = {
        "door": DOOR_TEMPLATES,
        "double-door": DOUBLE_DOOR_TEMPLATES,
        "window": WINDOW_TEMPLATES,
        "double-window": DOUBLE_WINDOW_TEMPLATES,
    }

    results = {k: {"confirm": [], "oblique": [], "reject": []} for k in EXPORTS}
    used_boxes = []

    for label, folder in EXPORTS.items():
        print(f"\n========== {label.upper()} ==========")
        templates = load_templates(folder)
        if not templates:
            print(f"[WARN] Niciun template pentru {label}")
            continue

        relevant = []
        for p in preds:
            cls = _norm_class(str(p.get("class", "")))
            if label == "door" and ("door" in cls and "double" not in cls):
                relevant.append(p)
            elif label == "double-door" and ("double" in cls and "door" in cls):
                relevant.append(p)
            elif label == "window" and ("window" in cls and "double" not in cls):
                relevant.append(p)
            elif label == "double-window" and ("double" in cls and "window" in cls):
                relevant.append(p)

        for i, pred in enumerate(relevant, 1):
            x, y, w, h = (
                int(pred.get("x", 0)),
                int(pred.get("y", 0)),
                int(pred.get("width", 0)),
                int(pred.get("height", 0)),
            )
            conf = float(pred.get("confidence", 0.0))
            x1, y1, x2, y2 = (
                max(0, x - w // 2),
                max(0, y - h // 2),
                min(img.shape[1], x + w // 2),
                min(img.shape[0], y + h // 2),
            )
            crop = gray[y1:y2, x1:x2]
            if crop.size == 0:
                continue

            # suprapuneri
            if any(overlap((x1, y1, x2, y2), b) > 0.4 for b in used_boxes):
                print(f"   #{i} suprapus cu o detecție existentă — ignorat.")
                continue

            best_sim = match_with_rotation(crop, templates, scales)
            combined = (0.6 * conf) + (0.4 * best_sim)
            print(f"   #{i} conf={conf:.2f}, sim={best_sim:.3f}, combined={combined:.3f}")

            if combined >= 0.50 and best_sim > TEMPLATE_SIMILARITY:
                results[label]["confirm"].append((x1, y1, x2, y2))
                used_boxes.append((x1, y1, x2, y2))
            else:
                tmp_path = TEMP_DIR / f"maybe_{label}_{i}.jpg"
                cv2.imwrite(str(tmp_path), crop)
                try:
                    sample_template = next(folder.glob("*.png"))
                    if ask_gemini(str(sample_template), str(tmp_path), label):
                        results[label]["oblique"].append((x1, y1, x2, y2))
                        used_boxes.append((x1, y1, x2, y2))
                    else:
                        results[label]["reject"].append((x1, y1, x2, y2))
                except StopIteration:
                    print(f"[WARN] Niciun template pentru {label}")

    out = img.copy()
    detections_export = []

    for label in results:
        for (x1, y1, x2, y2) in results[label]["confirm"]:
            cv2.rectangle(out, (x1, y1), (x2, y2), COLORS[label]["template"], 2)
            detections_export.append(
                {
                    "type": label,
                    "status": "confirmed",
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                }
            )
        for (x1, y1, x2, y2) in results[label]["oblique"]:
            cv2.rectangle(out, (x1, y1), (x2, y2), COLORS[label]["gemini"], 2)
            detections_export.append(
                {
                    "type": label,
                    "status": "gemini",
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                }
            )
        for (x1, y1, x2, y2) in results[label]["reject"]:
            detections_export.append(
                {
                    "type": label,
                    "status": "rejected",
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                }
            )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT_PATH), out)

    record_image(
        OUT_PATH,
        stage="count_objects",
        caption="Detecții finale: uși/ferestre (confirmate + oblice) marcate pe plan.",
    )
    with open(DETECTIONS_JSON, "w", encoding="utf-8") as f:
        json.dump(detections_export, f, indent=2, ensure_ascii=False)
    record_json(
        DETECTIONS_JSON,
        stage="count_objects",
        caption="Lista consolidată a detecțiilor: tip, status, bboxes.",
    )

    print(f"\n✅ Imagine finală curată salvată: {OUT_PATH}")
    print(f"📄 JSON cu detecțiile salvat în: {DETECTIONS_JSON}")
    print(f"   Total: {len(detections_export)} elemente exportate\n")

    for cls in results:
        print(
            f"🔹 {cls}: {len(results[cls]['confirm'])} confirmate | "
            f"{len(results[cls]['oblique'])} Gemini | "
            f"{len(results[cls]['reject'])} respinse"
        )


if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        main_single_plan()
    else:
        cwd_backup = Path.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = Path(plan_dir)
            print(
                f"\n================= PLAN (detect_openings_hybrid): {plan_path} ================="
            )

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
