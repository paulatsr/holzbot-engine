# ==============================================
# detect_exterior_doors.py — versiune completă (fix automată pentru exterior)
# ==============================================
import cv2
import json
import numpy as np
from pathlib import Path
import subprocess, sys, math
from ui_export import record_image, record_json
import os  # ← adăugat pentru MULTI_PLANS

# ==============================================
# CONFIG
# ==============================================
PLAN_PATH = Path("plan.jpg")
DETECTIONS_JSON = Path("count_objects/detections_all.json")
ROOM_EXTRACTION_SCRIPT = Path("exterior_doors/room_extraction.py")
LABELS_PATH = Path("exterior_doors/rooms_labels.npy")
ROOMS_DATA_PATH = Path("exterior_doors/rooms_data.json")
OUTPUT_DIR = Path("exterior_doors")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_IMG = OUTPUT_DIR / "exterior_doors_detected.jpg"
OUT_JSON = OUTPUT_DIR / "exterior_doors.json"

# ==============================================
def run_room_extraction():
    """Rulează automat scriptul room_extraction.py dacă nu există fișierele necesare."""
    print("🏗️ Rulez room_extraction.py ...")
    subprocess.run([sys.executable, str(ROOM_EXTRACTION_SCRIPT)], check=True)

# ==============================================
def main_single_plan():
    # VERIFICĂ EXISTENȚA INPUTURILOR
    # ==============================================
    if not LABELS_PATH.exists() or not ROOMS_DATA_PATH.exists():
        run_room_extraction()

    if not DETECTIONS_JSON.exists():
        raise FileNotFoundError(f"❌ Nu am găsit {DETECTIONS_JSON}")

    plan_img = cv2.imread(str(PLAN_PATH))
    if plan_img is None:
        raise FileNotFoundError(f"❌ Nu pot citi imaginea: {PLAN_PATH}")

    mask = np.load(str(LABELS_PATH))
    with open(ROOMS_DATA_PATH, "r", encoding="utf-8") as f:
        rooms_data = json.load(f)
    with open(DETECTIONS_JSON, "r", encoding="utf-8") as f:
        detections = json.load(f)

    overlay = plan_img.copy()
    H_mask, W_mask = mask.shape[:2]
    H_plan, W_plan = plan_img.shape[:2]
    scale_x = W_mask / W_plan
    scale_y = H_mask / H_plan

    # ==============================================
    # DISTANCE TRANSFORM — cu fallback automat pentru exterior
    # ==============================================
    exterior_labels = set(rooms_data.get("exterior_labels", []))

    # ✅ fallback automat: dacă exterior_labels lipsește, îl deduce din rooms list
    if not exterior_labels:
        print("⚠️  Nu s-au găsit 'exterior_labels' în JSON — încerc deducerea automată...")
        if "rooms" in rooms_data:
            exterior_labels = {r["id"] for r in rooms_data["rooms"] if r.get("is_exterior")}
        if not exterior_labels:
            raise ValueError("❌ Nu există camere marcate ca exterior (is_exterior=true) în JSON!")
        else:
            print(f"✅ Exterior dedus automat: {sorted(exterior_labels)}")

    # Creează o mască binară pentru exterior
    exterior_mask = np.isin(mask, list(exterior_labels)).astype(np.uint8)

    # Distance transform: cât de departe e fiecare pixel de exterior
    dist_to_exterior = cv2.distanceTransform(1 - exterior_mask, cv2.DIST_L2, 5)
    print(f"📏 Harta distanței față de exterior calculată corect (cu {len(exterior_labels)} labeluri).")

    # ==============================================
    def distance_to_exterior(x1, y1, x2, y2):
        """Returnează distanța minimă de la o ușă la zona exterioară (în pixeli)."""
        x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(W_mask - 1, x2), min(H_mask - 1, y2)
        patch = dist_to_exterior[y1:y2, x1:x2]
        if patch.size == 0:
            return float("inf")
        return float(np.min(patch))

    # ==============================================
    # DETECTARE UȘI EXTERIOARE / INTERIOARE
    # ==============================================
    exterior_doors = []
    print("\n================= 🧩 ANALIZĂ UȘI =================")

    for idx, det in enumerate(detections, start=1):
        label = (det.get("type") or det.get("class") or "").lower()
        if "door" not in label:
            continue

        # Scalare coordonate la dimensiunile măștii
        x1, y1, x2, y2 = map(int, [
            det["x1"] * scale_x, det["y1"] * scale_y,
            det["x2"] * scale_x, det["y2"] * scale_y
        ])

        door_w, door_h = x2 - x1, y2 - y1
        diag = math.sqrt(door_w**2 + door_h**2)
        min_dist = distance_to_exterior(x1, y1, x2, y2)
        proximity = min_dist / (0.5 * diag) if diag > 0 else float("inf")

        # Clasificare
        if proximity <= 1.0:
            status, color = "exterior", (0, 0, 255)
            reason = f"{min_dist:.1f}px < 0.5×diag ({0.5*diag:.1f}px)"
        else:
            status, color = "interior", (0, 255, 0)
            reason = f"{min_dist:.1f}px > 0.5×diag ({0.5*diag:.1f}px)"

        # LOG
        print(f"\n[{idx}] 🟩 UȘĂ #{idx}")
        print(f"   ➤ Tip: {label}")
        print(f"   ➤ Coordonate: ({x1},{y1}) - ({x2},{y2})")
        print(f"   ➤ Lățime={door_w}px, Înălțime={door_h}px, Diagonală={diag:.1f}px")
        print(f"   ➤ Distanță minimă față de exterior: {min_dist:.1f}px")
        print(f"   ➤ Raport proximity: {proximity:.3f}")
        print(f"   ➤ Decizie: {status.upper()} ({reason})")

        # DESEN
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        label_text = f"#{idx} {status[:3].upper()}"
        reason_text = f"{min_dist:.1f}px→ext"
        cv2.putText(overlay, label_text, (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        cv2.putText(overlay, reason_text, (x1, y2 + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

        exterior_doors.append({
            "id": idx,
            "type": label,
            "status": status,
            "bbox": [x1, y1, x2, y2],
            "diag": round(diag, 2),
            "min_dist_to_exterior": round(min_dist, 2),
            "proximity_ratio": round(proximity, 3),
            "reason": reason
        })

    # ==============================================
    # SALVARE
    # ==============================================
    cv2.imwrite(str(OUT_IMG), overlay)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(exterior_doors, f, indent=2, ensure_ascii=False)

    record_image(OUT_IMG, stage="exterior_doors",
                 caption="Uși clasificate: EXTERIOR vs INTERIOR (distanță față de exterior).")
    record_json(OUT_JSON, stage="exterior_doors",
                caption="Tabel uși cu bbox, distanțe, motive decizie.")

    num_ext = sum(1 for d in exterior_doors if d["status"] == "exterior")
    num_int = sum(1 for d in exterior_doors if d["status"] == "interior")

    print("\n================= 🧾 REZUMAT =================")
    print(f"✅ Uși interioare: {num_int}")
    print(f"✅ Uși exterioare: {num_ext}")
    print(f"📄 JSON: {OUT_JSON}")
    print(f"🖼️ Imagine: {OUT_IMG}")


if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        # comportament original: un singur plan
        main_single_plan()
    else:
        cwd_backup = Path.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = Path(plan_dir)
            print(f"\n================= PLAN (detect_exterior_doors): {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
