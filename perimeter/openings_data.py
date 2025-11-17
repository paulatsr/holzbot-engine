import json
from pathlib import Path
from ui_export import record_json
import os  # pentru MULTI_PLANS

OUTPUT_PATH = Path("perimeter/openings_all.json")


def _plan_id() -> str | None:
    plan_id = os.getenv("PLAN_ID")
    if plan_id:
        plan_id = plan_id.strip()
    return plan_id or None


def _plan_output_path(base_path: Path) -> Path | None:
    plan_id = _plan_id()
    if not plan_id:
        return None
    return base_path.with_name(f"{base_path.stem}_{plan_id}{base_path.suffix}")


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _aggregate_openings(base_path: Path):
    """
    Combină toate openings_all_pXX.json într-o singură listă pentru faza de
    house_pricing și pentru PDF.
    """
    plan_files = sorted(base_path.parent.glob(f"{base_path.stem}_p*.json"))
    if not plan_files:
        return

    combined = []
    for pf in plan_files:
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
            if isinstance(data, list):
                combined.extend(data)
        except Exception:
            continue

    if not combined:
        return

    for idx, item in enumerate(combined, start=1):
        if isinstance(item, dict):
            item["id"] = idx

    _write_json(base_path, combined)

# ==============================================
# CONFIG
# ==============================================
DETECTIONS_PATH = Path("count_objects/detections_all.json")
MEASUREMENTS_PATH = Path("measure_objects/openings_measurements_gemini.json")
EXTERIOR_DOORS_PATH = Path("exterior_doors/exterior_doors.json")
OUTPUT_PATH_STR = str(OUTPUT_PATH)

def main_single_plan():
    # ==============================================
    # VERIFICĂ EXISTENȚA FIȘIERELOR
    # ==============================================
    for p in [DETECTIONS_PATH, MEASUREMENTS_PATH]:
        if not p.exists():
            raise FileNotFoundError(f"❌ Lipsă fișier: {p}")

    with open(DETECTIONS_PATH, "r", encoding="utf-8") as f:
        detections = json.load(f)

    with open(MEASUREMENTS_PATH, "r", encoding="utf-8") as f:
        meas = json.load(f)

    # exterior_doors.json e opțional (poate nu e rulat încă)
    if EXTERIOR_DOORS_PATH.exists():
        with open(EXTERIOR_DOORS_PATH, "r", encoding="utf-8") as f:
            exterior_data = json.load(f)
        # mapăm ușile după coordonate aproximative (rotunjite)
        door_status_map = {}
        for d in exterior_data:
            key = tuple(map(int, d["bbox"]))
            door_status_map[key] = d["status"]
    else:
        print("⚠️  Lipsă exterior_doors.json — toate ușile vor fi marcate ca 'unknown'")
        door_status_map = {}

    # ==============================================
    # FUNCTIE PENTRU EXTRAGERE LĂȚIME VALIDATĂ
    # ==============================================
    def get_width_for_type(t):
        key = t.lower().replace("-", "_")
        item = meas.get(key)
        if not item:
            return None
        return (
            item.get("validated_width_meters")
            or item.get("real_width_meters")
            or item.get("pixel_width_estimated")
        )

    # ==============================================
    # CREARE STRUCTURĂ FINALĂ
    # ==============================================
    openings = []
    id_counter = 1

    for det in detections:
        obj_type = det.get("type", "").lower()
        if not any(k in obj_type for k in ["door", "window"]):
            continue

        # determinăm tipul standard (door / double_door / window / double_window)
        if "double" in obj_type and "door" in obj_type:
            key = "double_door"
        elif "double" in obj_type and "window" in obj_type:
            key = "double_window"
        elif "door" in obj_type:
            key = "door"
        elif "window" in obj_type:
            key = "window"
        else:
            continue

        width_m = get_width_for_type(key)
        if width_m is None:
            print(f"⚠️  Tip necunoscut în measurements: {key}")
            continue

        # status (interior/exterior) doar pentru uși
        status = "exterior" if "window" in key else "unknown"
        if "door" in key:
            bbox = tuple(map(int, [det["x1"], det["y1"], det["x2"], det["y2"]]))
            # cautăm un match în exterior_doors.json
            for k, v in door_status_map.items():
                # comparăm cu toleranță (ușile YOLO nu au coordonate exact identice)
                if all(abs(a - b) < 15 for a, b in zip(k, bbox)):
                    status = v
                    break

        openings.append({
            "id": id_counter,
            "type": key,
            "status": status,
            "width_m": round(float(width_m), 3)
        })
        id_counter += 1

    # ==============================================
    # SALVARE
    # ==============================================
    _write_json(OUTPUT_PATH, openings)

    plan_output = _plan_output_path(OUTPUT_PATH)
    if plan_output is not None:
        _write_json(plan_output, openings)
        _aggregate_openings(OUTPUT_PATH)

    record_json(OUTPUT_PATH_STR, stage="perimeter",
                caption="Deschideri standardizate (uși/ferestre) cu lățimi (m) + status.")

    print(f"✅ Fișier generat: {OUTPUT_PATH}")
    print(f"   Total obiecte: {len(openings)}")
    print(json.dumps(openings[:10], indent=2, ensure_ascii=False))  # primele 10


if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        # comportament original
        main_single_plan()
    else:
        cwd_backup = Path.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = Path(plan_dir)
            print(f"\n================= PLAN (openings_data): {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
