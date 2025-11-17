#!/usr/bin/env python3
import json, os, datetime
from ui_export import record_json
from pathlib import Path  # ← pentru MULTI_PLANS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AREA_PATH = os.path.join(BASE_DIR, "area", "house_area_gemini.json")
COEFF_PATH = os.path.join(os.path.dirname(__file__), "coefficients.heating.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "output_heating.json")

def load_area(path=AREA_PATH):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return float(data["surface_estimation"]["final_area_m2"]), data

def load_coefficients(path=COEFF_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    area_m2, area_raw = load_area()
    coeff = load_coefficients()
    base_coef = float(coeff["coefficient_heating_per_m2"])
    chosen_type = coeff.get("type", "gaz")
    type_map = coeff.get("type_coefficients", {})
    type_coef = float(type_map.get(chosen_type, 1.0))
    total = round(area_m2 * base_coef * type_coef, 2)

    out = {
        "meta": {
            "component": "heating",
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "currency": coeff.get("currency", "RON"),
            "area_source": "surface_estimation.final_area_m2"
        },
        "inputs": {
            "area_m2": area_m2,
            "coefficient_heating_per_m2": base_coef,
            "type": chosen_type,
            "type_coefficient": type_coef
        },
        "calculation": {
            "formula": "area_m2 * coefficient_heating_per_m2 * type_coefficient",
            "result": total
        },
        "debug": {
            "area_raw": area_raw
        }
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    record_json(OUTPUT_PATH, stage="pricing",
            caption="Estimare cost încălzire (coef bază * tip * aria).")
    
    print(f"Heating price saved to: {OUTPUT_PATH}  total={total} {out['meta']['currency']}")

if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        # comportament original: un singur plan
        main()
    else:
        cwd_backup = Path.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = Path(plan_dir)
            print(f"\n================= PLAN (calculate_heating): {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main()
            finally:
                os.chdir(cwd_backup)
