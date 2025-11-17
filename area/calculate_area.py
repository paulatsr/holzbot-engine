import json
from pathlib import Path
import os

# ==============================================
# CONFIGURARE
# ==============================================
walls_file = Path("perimeter/walls_measurements_gemini.json")
openings_file = Path("measure_objects/openings_measurements_gemini.json")
detections_file = Path("count_objects/detections_all.json")
exterior_doors_file = Path("exterior_doors/exterior_doors.json")
output_file = Path("area/wall_areas_combined.json")

# ==============================================
# FUNCȚIE UTILĂ
# ==============================================
def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"❌ Lipsă fișier: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ==============================================
# FUNCȚIA PENTRU UN SINGUR PLAN
# (logica originală, 1:1, doar împachetată)
# ==============================================
def main_single_plan():
    # ==============================================
    # ÎNCĂRCARE DATE
    # ==============================================
    walls_data = load_json(walls_file)
    openings_data = load_json(openings_file)
    detections_data = load_json(detections_file)
    exterior_doors_data = load_json(exterior_doors_file)

    # ==============================================
    # EXTRAGERE LUNGIMI PEREȚI DIN GEMINI
    # ==============================================
    avg_data = walls_data.get("estimations", {}).get("average_result", {})
    interior_length = avg_data.get("interior_meters")
    exterior_length = avg_data.get("exterior_meters")

    if interior_length is None or exterior_length is None:
        raise ValueError("❌ Nu s-au găsit valorile pentru pereți în fișierul Gemini!")

    print(f"📏 Lungime pereți interiori: {interior_length:.2f} m")
    print(f"📏 Lungime pereți exteriori: {exterior_length:.2f} m")

    # ==============================================
    # VALORI STANDARD GERMANIA (DIN 277)
    # ==============================================
    WALL_HEIGHT_M = 2.5
    DOOR_HEIGHT_M = 2.05
    WINDOW_HEIGHT_M = 1.25

    # ==============================================
    # CALCUL ARII PEREȚI
    # ==============================================
    interior_walls_area = interior_length * WALL_HEIGHT_M
    exterior_walls_area = exterior_length * WALL_HEIGHT_M

    # ==============================================
    # EXTRAGERE LĂȚIMI DESCHIDERI DIN GEMINI
    # ==============================================
    def get_width(data, key):
        if key not in data:
            return 0.0
        val = (
            data[key].get("validated_width_meters")
            or data[key].get("real_width_meters")
            or data[key].get("pixel_width_estimated")
            or 0.0
        )
        return float(val)

    door_w = get_width(openings_data, "door")
    double_door_w = get_width(openings_data, "double_door")
    window_w = get_width(openings_data, "window")
    double_window_w = get_width(openings_data, "double_window")

    if double_door_w == 0.0:
        double_door_w = door_w * 2

    # ==============================================
    # NUMĂRĂRILE AUTOMATE DIN DETECȚII
    # ==============================================
    valid_detections = [d for d in detections_data if d.get("status") != "rejected"]

    # Numără doar tipurile exacte (fără substring)
    num_doors_total = sum(1 for d in valid_detections if d["type"] == "door")
    num_windows = sum(1 for d in valid_detections if d["type"] == "window")
    num_double_windows = sum(1 for d in valid_detections if d["type"] == "double-window")

    # Uși interioare/exterioare din exterior_doors.json
    num_doors_exterior = sum(1 for d in exterior_doors_data if d["status"] == "exterior")
    num_doors_interior = sum(1 for d in exterior_doors_data if d["status"] == "interior")

    print("\n========= 📊 DETECȚII =========")
    print(f"🚪 Uși totale: {num_doors_total}")
    print(f"   → Interioare: {num_doors_interior}")
    print(f"   → Exterioare: {num_doors_exterior}")
    print(f"🪟 Ferestre simple: {num_windows}")
    print(f"🪟 Ferestre duble: {num_double_windows}")
    print("===============================\n")

    # ==============================================
    # CALCUL ARII DESCHIDERI
    # ==============================================
    area_doors_int = num_doors_interior * door_w * DOOR_HEIGHT_M
    area_doors_ext = num_doors_exterior * door_w * DOOR_HEIGHT_M
    area_windows_ext = (num_windows * window_w * WINDOW_HEIGHT_M) + \
                       (num_double_windows * double_window_w * WINDOW_HEIGHT_M)

    # ==============================================
    # CALCUL ARII NETE
    # ==============================================
    net_exterior = exterior_walls_area - (area_doors_ext + area_windows_ext)
    net_interior = interior_walls_area - area_doors_int

    # ==============================================
    # STRUCTURĂ JSON FINALĂ
    # ==============================================
    result = {
        "source_files": {
            "walls": str(walls_file),
            "openings": str(openings_file),
            "detections": str(detections_file),
            "exterior_doors": str(exterior_doors_file)
        },
        "standards": {
            "country": "Germany",
            "standard": "DIN 277",
            "wall_height_m": WALL_HEIGHT_M,
            "door_height_m": DOOR_HEIGHT_M,
            "window_height_m": WINDOW_HEIGHT_M,
            "notes": "Înălțimi tipice pentru construcții rezidențiale din lemn."
        },
        "counts": {
            "doors_total": num_doors_total,
            "doors_interior": num_doors_interior,
            "doors_exterior": num_doors_exterior,
            "windows_simple": num_windows,
            "windows_double": num_double_windows
        },
        "widths_m": {
            "door": round(door_w, 2),
            "double_door": round(double_door_w, 2),
            "window": round(window_w, 2),
            "double_window": round(double_window_w, 2)
        },
        "areas_m2": {
            "walls": {
                "interior_total": round(interior_walls_area, 2),
                "exterior_total": round(exterior_walls_area, 2)
            },
            "openings": {
                "doors_interior": round(area_doors_int, 2),
                "doors_exterior": round(area_doors_ext, 2),
                "windows_exterior": round(area_windows_ext, 2),
                "openings_exterior_total": round(area_doors_ext + area_windows_ext, 2)
            },
            "net_walls": {
                "interior_net": round(net_interior, 2),
                "exterior_net": round(net_exterior, 2)
            },
            "summary": {
                "gross_total": round(interior_walls_area + exterior_walls_area, 2),
                "openings_total": round(area_doors_int + area_doors_ext + area_windows_ext, 2),
                "net_total": round(net_interior + net_exterior, 2)
            }
        },
        "notes": (
            "Scriptul a calculat automat ariile pereților și ale deschiderilor pe baza "
            "fișierelor de detecție și a dimensiunilor estimate de Gemini. "
            "Ferestrele duble și simple sunt tratate separat. "
            "Ușile exterioare contribuie la aria exterioară, iar cele interioare la aria internă."
        )
    }

    # ==============================================
    # SALVARE ȘI AFIȘARE
    # ==============================================
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"✅ Rezultatele au fost salvate în {output_file}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


# ==============================================
# SUPORT PENTRU N PLANURI (1–10) PRIN MULTI_PLANS
# ==============================================
if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    # ✅ Comportament vechi: un singur plan, în directorul curent
    if not plans_env:
        main_single_plan()
    else:
        from pathlib import Path as _Path

        cwd_backup = _Path.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = _Path(plan_dir)
            print(f"\n================= PLAN: {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
