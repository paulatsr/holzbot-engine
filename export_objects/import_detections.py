# engine/export_objects/import_detections.py
import os, sys, json, shutil, time
from pathlib import Path
import requests
from ui_export import record_json, record_text

# încarcă .env dacă rulezi direct
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

API_KEY   = (os.getenv("ROBOFLOW_API_KEY") or "").strip()
PROJECT   = (os.getenv("ROBOFLOW_PROJECT") or "house-plan-uwkew").strip()
VERSION   = (os.getenv("ROBOFLOW_VERSION") or "5").strip()

PLAN_PATH   = "plan.jpg"
OUT_PATH    = Path("export_objects/detections.json")
EXPORTS_DIR = Path("exports")
CONF        = 0.5   # 0..1
OVERLAP     = 30    # 0..100

# Endpoint corect pentru object detection
DETECT_URL = f"https://detect.roboflow.com/{PROJECT}/{VERSION}"

def clear_exports_folder():
    if EXPORTS_DIR.exists():
        print(f"[CLEANUP] Șterg conținutul folderului {EXPORTS_DIR}...")
        for item in EXPORTS_DIR.iterdir():
            try:
                if item.is_file() or item.is_symlink(): item.unlink()
                elif item.is_dir(): shutil.rmtree(item)
            except Exception as e:
                print(f"[WARN] Nu s-a putut șterge {item}: {e}")
    else:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Folderul {EXPORTS_DIR} a fost creat.")

def main():
    print(f"[DEBUG] key_len={len(API_KEY)} proj='{PROJECT}' v={VERSION}")
    if not API_KEY:
        msg = "[ERROR] ROBOFLOW_API_KEY lipsește din .env"
        print(msg); record_text(msg, stage="export_objects"); sys.exit(1)
    if not Path(PLAN_PATH).exists():
        msg = f"[ERROR] Nu găsesc {PLAN_PATH} în {Path.cwd()}"
        print(msg); record_text(msg, stage="export_objects"); sys.exit(1)

    clear_exports_folder()
    params = {
        "api_key": API_KEY,
        "confidence": int(CONF * 100),  # 0..100
        "overlap": OVERLAP
    }
    print(f"[INFO] Detect API → {DETECT_URL}  params={params}")

    start = time.time()
    with open(PLAN_PATH, "rb") as f:
        # multipart/form-data (corect pentru detect.roboflow.com)
        files = { "file": ("plan.jpg", f, "image/jpeg") }
        r = requests.post(DETECT_URL, params=params, files=files, timeout=120)
    elapsed = time.time() - start

    if r.status_code != 200:
        msg = f"[ERROR] Detect HTTP {r.status_code}: {r.text[:400]}"
        print(msg); record_text(msg, stage="export_objects"); sys.exit(1)

    try:
        result = r.json()
    except Exception:
        msg = f"[ERROR] Răspuns non-JSON: {r.text[:400]}"
        print(msg); record_text(msg, stage="export_objects"); sys.exit(1)

    preds = result.get("predictions", [])
    print(f"[DONE] {len(preds)} detecții în {elapsed:.2f}s")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    record_json(OUT_PATH, stage="export_objects")
    print(f"[OK] JSON salvat în: {OUT_PATH.as_posix()}")

if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        # Comportament original
        main()
    else:
        cwd_backup = Path.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = Path(plan_dir)
            print(f"\n================= PLAN (import_detections): {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main()
            finally:
                os.chdir(cwd_backup)
