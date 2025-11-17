import json
from ui_export import record_json
import os
from pathlib import Path

OUTPUT_FILE = Path("area/wall_areas_from_gemini.json")


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


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _aggregate_wall_areas(base_path: Path):
    """
    După ce avem fișiere wall_areas_from_gemini_pXX.json, generăm un rezumat
    cumulat astfel încât price_summary_full + alte scripturi să lucreze cu totalul.
    """
    plan_files = sorted(base_path.parent.glob(f"{base_path.stem}_p*.json"))
    if not plan_files:
        return

    total_interior_len = 0.0
    total_exterior_len = 0.0
    total_int_area = 0.0
    total_ext_area = 0.0
    breakdown = []
    standards = None

    for pf in plan_files:
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
        except Exception:
            continue

        if standards is None:
            standards = data.get("standards")

        inputs = data.get("inputs", {})
        comp = data.get("computed_areas", {})
        interior_len = float(inputs.get("interior_length_m") or 0.0)
        exterior_len = float(inputs.get("exterior_length_m") or 0.0)
        interior_area = float(comp.get("interior_walls_area_m2") or 0.0)
        exterior_area = float(comp.get("exterior_walls_area_m2") or 0.0)

        total_interior_len += interior_len
        total_exterior_len += exterior_len
        total_int_area += interior_area
        total_ext_area += exterior_area

        breakdown.append({
            "plan_file": pf.name,
            "interior_walls_area_m2": round(interior_area, 2),
            "exterior_walls_area_m2": round(exterior_area, 2)
        })

    if total_int_area <= 0 and total_ext_area <= 0:
        return

    aggregate = {
        "source_file": "aggregated_from_plans",
        "standards": standards,
        "inputs": {
            "interior_length_m": round(total_interior_len, 2),
            "exterior_length_m": round(total_exterior_len, 2)
        },
        "computed_areas": {
            "interior_walls_area_m2": round(total_int_area, 2),
            "exterior_walls_area_m2": round(total_ext_area, 2),
            "total_walls_area_m2": round(total_int_area + total_ext_area, 2)
        },
        "plans": breakdown,
        "notes": "Sumă multi-plan a ariilor pereților (DIN 277)."
    }

    _write_json(base_path, aggregate)

# 📂 Fișierul sursă
input_file = "perimeter/walls_measurements_gemini.json"
output_file = str(OUTPUT_FILE)

def main_single_plan():
    # 🔽 Citește lungimile din fișierul Gemini
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Extrage valorile medii din JSON
    avg_data = data.get("estimations", {}).get("average_result", {})

    interior_length = avg_data.get("interior_meters")
    exterior_length = avg_data.get("exterior_meters")

    if interior_length is None or exterior_length is None:
        raise ValueError("❌ Nu s-au găsit valorile medii pentru pereți în fișierul Gemini!")

    print(f"📏 Lungime pereți interiori: {interior_length} m")
    print(f"📏 Lungime pereți exteriori: {exterior_length} m")

    # 🧱 Înălțime standard a pereților în Germania (DIN 277)
    WALL_HEIGHT_M = 2.5

    # 🔹 Calculează ariile
    interior_area = round(interior_length * WALL_HEIGHT_M, 2)
    exterior_area = round(exterior_length * WALL_HEIGHT_M, 2)
    total_area = round(interior_area + exterior_area, 2)

    # 🔹 Structură JSON finală
    result = {
        "source_file": input_file,
        "standards": {
            "country": "Germany",
            "wall_height_m": WALL_HEIGHT_M,
            "standard": "DIN 277",
            "description": "Standard German de dimensionare spațială — înălțimea tipică a pereților în locuințe rezidențiale."
        },
        "inputs": {
            "interior_length_m": interior_length,
            "exterior_length_m": exterior_length
        },
        "computed_areas": {
            "interior_walls_area_m2": interior_area,
            "exterior_walls_area_m2": exterior_area,
            "total_walls_area_m2": total_area
        },
        "notes": (
            "Ariile au fost calculate automat pe baza valorilor medii din walls_measurements_gemini.json. "
            "Rezultatele sunt în conformitate cu standardul german DIN 277, folosind o înălțime de 2.5m."
        )
    }

    # 💾 Salvează rezultatul în fișier
    _write_json(OUTPUT_FILE, result)

    plan_output = _plan_output_path(OUTPUT_FILE)
    if plan_output is not None:
        _write_json(plan_output, result)
        _aggregate_wall_areas(OUTPUT_FILE)

    record_json(output_file, stage="area",
                caption="Arii pereți (brut) – deschideri – net (interior/exterior) + sumar.")

    print(f"\n✅ Rezultatul a fost salvat în {output_file}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        # Comportament original: un singur plan
        main_single_plan()
    else:
        cwd_backup = Path.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = Path(plan_dir)
            print(f"\n================= PLAN: {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
