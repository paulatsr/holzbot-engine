# engine/export_objects/run_crops.py
import sys
from pathlib import Path

# === PATH shim: adaugă rădăcina proiectului (engine) în sys.path ===
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .../engine
# ===================================================================

import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

from ui_export import record_image, record_text

# ==============================================
# CONFIGURARE
# ==============================================
ROOT      = Path(__file__).resolve().parents[1]
IMAGE_PATH = ROOT / "plan.jpg"
JSON_PATH  = ROOT / "export_objects" / "detections.json"
OUT_ROOT   = ROOT / "export_objects" / "exports"

SCRIPTS = [
    ROOT / "export_objects" / "crop_door.py",
    ROOT / "export_objects" / "crop_double_door.py",
    ROOT / "export_objects" / "crop_window.py",
    ROOT / "export_objects" / "crop_double_window.py",
]

# ==============================================
# FUNCȚIE DE EXECUȚIE
# ==============================================
def run_script(script_path: Path):
    cmd = [
        str(Path(sys.executable)),  # python din același venv
        str(script_path),
        "--image", str(IMAGE_PATH),
        "--json", str(JSON_PATH),
        "--out-root", str(OUT_ROOT)
    ]
    print(f"[START] {script_path.name} ...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"[DONE] {script_path.name}")
        return (script_path.name, "OK", result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"[ERR] {script_path.name} a eșuat.")
        return (script_path.name, "ERR", e.stderr.strip())

def sample_indices(n: int, k: int) -> list[int]:
    if n <= 0 or k <= 0:
        return []
    if k >= n:
        return list(range(n))
    step = n / float(k)
    return [int(i * step) for i in range(k)]

# ==============================================
# EXECUȚIE
# ==============================================
def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    record_text("export_objects — start", stage="export_objects", filename="_00.txt", append=False)

    # pornesc toate cele 4 scripturi în paralel
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_script, s) for s in SCRIPTS]
        for fut in as_completed(futures):
            script, status, output = fut.result()
            msg = f"=== Rezultate {script} ({status}) ===\n{output}\n"
            record_text(msg, stage="export_objects")

    # selectez max 5 imagini pe sărite
    all_imgs = sorted([
        p for p in OUT_ROOT.rglob("*")
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ])
    total = len(all_imgs)
    if total == 0:
        record_text("Nu am găsit crop-uri în exports/", stage="export_objects")
    else:
        picks = sample_indices(total, 5)
        record_text(f"Selectez {len(picks)} din {total} imagini (sampling uniform)", stage="export_objects")
        for i in picks:
            try:
                record_image(str(all_imgs[i]), stage="export_objects")
            except Exception as e:
                record_text(f"[WARN] nu pot publica {all_imgs[i].name}: {e}", stage="export_objects")

    record_text("export_objects — done", stage="export_objects", filename="_99.txt", append=False)

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
            print(f"\n================= PLAN (run_crops): {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main()
            finally:
                os.chdir(cwd_backup)
