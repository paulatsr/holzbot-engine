# runner/segmentation/rooms_from_walls.py
import cv2
import numpy as np
from pathlib import Path
import json
import os

from runner.ui_export import record_image, record_file, record_json

PLAN_PATH = Path("plan.jpg")
OUTPUT_DIR = Path("exterior_doors")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

WALLS_PATH = OUTPUT_DIR / "walls_detected.jpg"
ROOMS_COLORED_PATH = OUTPUT_DIR / "rooms_colored.jpg"
ROOMS_DATA_PATH = OUTPUT_DIR / "rooms_data.json"
LABELS_PATH = OUTPUT_DIR / "rooms_labels.npy"

CANNY_LOW, CANNY_HIGH = 70, 160
DILATE_KERNEL = (3, 3)
DILATE_ITER = 1
CLOSE_KERNEL = (5, 5)


def main_single_plan():
    print(f"🏠 Analizez planul: {PLAN_PATH.name}")
    img = cv2.imread(str(PLAN_PATH))
    if img is None:
        raise FileNotFoundError("❌ Nu am găsit planul.")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    edges = cv2.Canny(gray, CANNY_LOW, CANNY_HIGH)
    walls = cv2.dilate(edges, np.ones(DILATE_KERNEL, np.uint8), iterations=DILATE_ITER)
    walls = cv2.morphologyEx(
        walls, cv2.MORPH_CLOSE, np.ones(CLOSE_KERNEL, np.uint8)
    )
    cv2.imwrite(str(WALLS_PATH), walls)
    print(f"🧱 Pereți detectați salvați în {WALLS_PATH.name}")

    rooms_mask = cv2.bitwise_not(walls)
    _, rooms_mask = cv2.threshold(rooms_mask, 127, 255, cv2.THRESH_BINARY)
    num_labels, labels = cv2.connectedComponents(rooms_mask)
    H, W = labels.shape
    print(f"🧩 {num_labels - 1} regiuni detectate (fără exteriorul)")

    flood_mask = np.zeros((H + 2, W + 2), np.uint8)
    filled = labels.copy()
    cv2.floodFill(filled, flood_mask, (0, 0), 9999)
    exterior_label = 9999

    colored = np.zeros((H, W, 3), dtype=np.uint8)
    colors = np.random.randint(0, 255, (num_labels + 1, 3), dtype=np.uint8)
    rooms = []

    for lbl in range(1, num_labels):
        mask = labels == lbl
        if not np.any(mask):
            continue
        colored[mask] = colors[lbl]
        rooms.append({"id": int(lbl), "is_exterior": False, "area": int(np.sum(mask))})

    colored[filled == exterior_label] = (180, 180, 180)
    rooms.append(
        {"id": 9999, "is_exterior": True, "area": int(np.sum(filled == 9999))}
    )

    cv2.imwrite(str(ROOMS_COLORED_PATH), colored)
    np.save(str(LABELS_PATH), filled)

    data = {
        "num_labels": int(num_labels),
        "rooms": rooms,
        "params": {
            "canny_low": CANNY_LOW,
            "canny_high": CANNY_HIGH,
            "dilate_kernel": DILATE_KERNEL,
            "close_kernel": CLOSE_KERNEL,
        },
    }

    with open(ROOMS_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    record_image(
        WALLS_PATH, stage="exterior_doors", caption="Pereți detectați (edge + morph)."
    )
    record_image(
        ROOMS_COLORED_PATH,
        stage="exterior_doors",
        caption="Camere segmentate + exterior (gri).",
    )
    record_file(LABELS_PATH, stage="exterior_doors", caption="Mască label-uri camere (npy).")
    record_json(
        ROOMS_DATA_PATH,
        stage="exterior_doors",
        caption="Meta-date camere + parametri detecție.",
    )

    print(f"✅ Date salvate în {ROOMS_DATA_PATH.name}")
    print(f"🏁 Cameră exterior marcată (label={exterior_label})")


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
                f"\n================= PLAN (rooms_from_walls): {plan_path} ================="
            )

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
