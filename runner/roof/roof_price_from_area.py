# runner/roof/roof_price_from_area.py
import os
import json
import math
import copy
from pathlib import Path
from datetime import datetime
import sys
import pathlib

from runner.ui_export import record_json

# ------------------------------
# Helpers: read UI selection
# ------------------------------
def _read_selection() -> dict:
    p = Path("roof/selected_roof.json")
    if not p.exists():
        return {}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
        return {
            "tipAcoperis": (j.get("tipAcoperis") or "").strip(),
            "materialAcoperis": (j.get("materialAcoperis") or "").strip().lower(),
        }
    except Exception:
        return {}


house_area_file = Path("area/house_area_gemini.json")
roof_types_file = Path("roof/roof_types_germany.json")
roof_coeffs_file = Path("roof/roof_coefficients.json")
roof_output_file = Path("roof/roof_price_estimation.json")


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"❌ Lipsă fișier: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


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


def _house_area_path_for_plan() -> Path:
    """Pentru multi-plan: folosește aria fiecărui plan, nu aria totală."""
    plan_specific = _plan_output_path(house_area_file)
    if plan_specific and plan_specific.exists():
        return plan_specific
    return house_area_file


def _aggregate_roof_outputs() -> dict | None:
    """Combină roof_price_estimation_pXX.json într-un singur fișier total."""
    plan_files = sorted(roof_output_file.parent.glob(f"{roof_output_file.stem}_p*.json"))
    if not plan_files:
        return None

    plans_data = []
    for pf in plan_files:
        try:
            plans_data.append((pf.name, json.loads(pf.read_text(encoding="utf-8"))))
        except Exception:
            continue

    if not plans_data:
        return None

    if all("components" in data for _, data in plans_data):
        totals = {
            "roof_base_min": 0.0,
            "roof_base_max": 0.0,
            "roof_base_avg": 0.0,
            "sheet_metal": 0.0,
            "extra_walls": 0.0,
            "insulation": 0.0,
            "material": 0.0,
            "final_total": 0.0,
        }
        area_sum = 0.0
        perimeter_sum = 0.0
        breakdown = []

        for name, data in plans_data:
            comps = data["components"]
            totals["roof_base_min"] += float(comps["roof_base"].get("min_total_eur", 0.0))
            totals["roof_base_max"] += float(comps["roof_base"].get("max_total_eur", 0.0))
            totals["roof_base_avg"] += float(
                comps["roof_base"].get("average_total_eur", 0.0)
            )
            totals["sheet_metal"] += float(
                comps.get("sheet_metal", {}).get("total_eur", 0.0)
            )
            totals["extra_walls"] += float(
                comps.get("extra_walls", {}).get("total_eur", 0.0)
            )
            totals["insulation"] += float(
                comps.get("insulation", {}).get("total_eur", 0.0)
            )
            totals["material"] += float(
                comps.get("material", {}).get("total_eur", 0.0)
            )
            totals["final_total"] += float(data.get("roof_final_total_eur") or 0.0)

            area = float(data.get("inputs", {}).get("house_area_m2") or 0.0)
            perimeter = float(data.get("inputs", {}).get("perimeter_m") or 0.0)
            area_sum += area
            perimeter_sum += perimeter

            breakdown.append(
                {
                    "plan_file": name,
                    "house_area_m2": round(area, 2),
                    "perimeter_m": round(perimeter, 2),
                    "roof_final_total_eur": round(
                        float(data.get("roof_final_total_eur") or 0.0), 2
                    ),
                }
            )

        first_inputs = copy.deepcopy(plans_data[0][1].get("inputs", {}))
        first_meta = copy.deepcopy(plans_data[0][1].get("meta", {}))
        first_inputs["house_area_m2"] = round(area_sum, 2)
        first_inputs["perimeter_m"] = round(perimeter_sum, 2)

        aggregate = {
            "meta": first_meta,
            "inputs": first_inputs,
            "components": {
                "roof_base": {
                    "min_total_eur": round(totals["roof_base_min"], 2),
                    "max_total_eur": round(totals["roof_base_max"], 2),
                    "average_total_eur": round(totals["roof_base_avg"], 2),
                },
                "sheet_metal": {
                    "total_eur": round(totals["sheet_metal"], 2),
                },
                "extra_walls": {
                    "total_eur": round(totals["extra_walls"], 2),
                },
                "insulation": {
                    "total_eur": round(totals["insulation"], 2),
                },
                "material": {
                    "total_eur": round(totals["material"], 2),
                },
            },
            "roof_final_total_eur": round(totals["final_total"], 2),
            "plans": breakdown,
            "plans_count": len(breakdown),
            "aggregated_from_plans": True,
        }
        return aggregate

    breakdown = []
    total_avg = 0.0
    template = copy.deepcopy(plans_data[-1][1])
    for name, data in plans_data:
        price = data.get("price_estimation") or {}
        avg_val = float(price.get("average_total_eur") or 0.0)
        total_avg += avg_val
        breakdown.append({"plan_file": name, "average_total_eur": round(avg_val, 2)})

    if "price_estimation" in template:
        template["price_estimation"]["average_total_eur"] = round(total_avg, 2)
    template["plans"] = breakdown
    template["plans_count"] = len(breakdown)
    template["aggregated_from_plans"] = True
    return template


def perimeter_from_area(area_m2: float) -> float:
    if area_m2 <= 0:
        return 0.0
    side = math.sqrt(area_m2)
    return 4.0 * side


def calc_roof_price_from_data(
    final_area_m2: float,
    roof_types: list[dict],
    roof_name_key: str,
    coeffs: dict,
    selected_material: str | None = None,
):
    currency = coeffs.get("currency", "EUR")

    perimeter_override = coeffs.get("perimeter_override_m", None)
    if perimeter_override is not None:
        try:
            perimeter_m = float(perimeter_override)
        except Exception:
            perimeter_m = perimeter_from_area(final_area_m2)
    else:
        perimeter_m = perimeter_from_area(final_area_m2)

    roof_overhang_m = float(coeffs.get("roof_overhang_m", 0.0))
    sheet_metal_price_per_m = float(coeffs.get("sheet_metal_price_per_m", 0.0))
    insulation_price_per_m2 = float(coeffs.get("insulation_price_per_m2", 0.0))

    roof = next(
        (
            r
            for r in roof_types
            if str(r.get("name_de", "")).lower() == roof_name_key.lower()
            or str(r.get("name_en", "")).lower() == roof_name_key.lower()
        ),
        None,
    )
    if not roof:
        raise ValueError(
            f"❌ Tipul de acoperiș '{roof_name_key}' nu a fost găsit în roof_types_germany.json"
        )

    cost_range = roof.get("cost_estimate_eur_per_m2")
    if (
        not isinstance(cost_range, list)
        or len(cost_range) != 2
        or "n/a" in cost_range
    ):
        raise ValueError(
            f"❌ Tipul '{roof.get('name_de', roof_name_key)}' nu are date valide pentru cost/m²."
        )
    cmin, cmax = float(cost_range[0]), float(cost_range[1])

    min_roof = final_area_m2 * cmin
    max_roof = final_area_m2 * cmax
    avg_roof = (min_roof + max_roof) / 2.0

    sheet_metal_total = perimeter_m * roof_overhang_m * sheet_metal_price_per_m
    extra_walls_price_per_m = float(roof.get("extra_walls_price_eur_per_m", 0.0))
    extra_walls_total = perimeter_m * extra_walls_price_per_m
    insulation_total = final_area_m2 * insulation_price_per_m2

    mat_norm = (selected_material or "").lower()
    unit_map = {
        "tigla": float(coeffs.get("tile_price_per_m2", 0.0)),
        "tabla": float(coeffs.get("metal_price_per_m2", 0.0)),
        "membrana": float(coeffs.get("membrane_price_per_m2", 0.0)),
    }
    material_unit = unit_map.get(mat_norm, 0.0)
    material_total = final_area_m2 * material_unit

    final_total = round(
        avg_roof + sheet_metal_total + extra_walls_total + insulation_total + material_total,
        2,
    )

    breakdown = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "currency": currency,
            "perimeter_source": "override in request/coeffs"
            if perimeter_override is not None
            else "estimated as 4*sqrt(area)",
        },
        "inputs": {
            "house_area_m2": round(final_area_m2, 2),
            "perimeter_m": round(perimeter_m, 2),
            "roof_type": {
                "name_de": roof["name_de"],
                "name_en": roof.get("name_en"),
                "description": roof.get("description"),
                "cost_range_eur_per_m2": [cmin, cmax],
                "extra_walls_price_eur_per_m": extra_walls_price_per_m,
            },
            "coefficients": {
                "roof_overhang_m": roof_overhang_m,
                "sheet_metal_price_per_m": sheet_metal_price_per_m,
                "insulation_price_per_m2": insulation_price_per_m2,
                "tile_price_per_m2": coeffs.get("tile_price_per_m2", 0.0),
                "metal_price_per_m2": coeffs.get("metal_price_per_m2", 0.0),
                "membrane_price_per_m2": coeffs.get("membrane_price_per_m2", 0.0),
            },
            "material": {
                "selected": mat_norm or None,
                "unit_price_eur_per_m2": material_unit,
            },
        },
        "components": {
            "roof_base": {
                "min_total_eur": round(min_roof, 2),
                "max_total_eur": round(max_roof, 2),
                "average_total_eur": round(avg_roof, 2),
            },
            "sheet_metal": {
                "formula": "perimeter_m * roof_overhang_m * sheet_metal_price_per_m",
                "total_eur": round(sheet_metal_total, 2),
            },
            "extra_walls": {
                "formula": "perimeter_m * extra_walls_price_eur_per_m",
                "total_eur": round(extra_walls_total, 2),
            },
            "insulation": {
                "formula": "house_area_m2 * insulation_price_per_m2",
                "total_eur": round(insulation_total, 2),
            },
            "material": {
                "formula": "house_area_m2 * material_unit_price_eur_per_m2",
                "total_eur": round(material_total, 2),
            },
        },
        "roof_final_total_eur": final_total,
    }
    return breakdown


def run_estimation(roof_key_from_ui: str, overrides: dict | None = None):
    house = load_json(_house_area_path_for_plan())
    final_area_m2 = float(house["surface_estimation"]["final_area_m2"])
    roof_types = load_json(roof_types_file)["dachformen"]
    default_coeffs = load_json(roof_coeffs_file)
    coeffs = {**default_coeffs, **(overrides or {})}

    sel = _read_selection()
    selected_material = (
        sel.get("materialAcoperis") or (overrides or {}).get("roof_material") or ""
    ).lower()

    result = calc_roof_price_from_data(
        final_area_m2, roof_types, roof_key_from_ui, coeffs, selected_material
    )

    plan_output = _plan_output_path(roof_output_file)
    if plan_output is not None:
        dump_json(plan_output, result)
        aggregate = _aggregate_roof_outputs()
        if aggregate:
            dump_json(roof_output_file, aggregate)
        else:
            dump_json(roof_output_file, result)
    else:
        dump_json(roof_output_file, result)

    record_json(
        roof_output_file,
        stage="roof",
        caption=f"Preț acoperiș ({result['inputs']['roof_type']['name_de']}): defalcare + material + total.",
    )
    return result


def main_single_plan(selected_arg: str | None = None):
    sel = _read_selection()
    selected = selected_arg or (
        sys.argv[1]
        if len(sys.argv) > 1
        else (sel.get("tipAcoperis") or os.getenv("ROOF_SELECTED") or "Walmdach")
    )
    res = run_estimation(selected)
    print(f"🏷️  Roof selected: {selected} | material: {sel.get('materialAcoperis') or '—'}")
    print("✅ Rezultatul a fost salvat în", roof_output_file)
    print(json.dumps(res, indent=2, ensure_ascii=False))


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
                f"\n================= PLAN (roof_price_from_area): {plan_path} ================="
            )

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
