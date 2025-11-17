# runner/services/heating_from_area.py

import json
from datetime import datetime

from runner.core.paths import (
    HOUSE_AREA_JSON,
    HEATING_COEFFS_JSON,
    HEATING_OUTPUT_JSON,
    ENERGY_SITE_COEFFS_JSON,
    OFFER_OVERRIDES_JSON,
)
from runner.core.multi_plan_runner import run_for_plans
from runner.ui_export import record_json


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_house_area() -> tuple[float, dict]:
    data = _load_json(HOUSE_AREA_JSON)
    area = float(
        data.get("surface_estimation", {}).get("final_area_m2")
            or data.get("area_m2")
            or 0.0
    )
    if area <= 0:
        raise ValueError(f"Area <= 0 în {HOUSE_AREA_JSON}")
    return area, data


def _get_heating_type(overrides: dict, coeff: dict) -> str:
    """
    Încearcă să ia tipul de încălzire din UI (offer_overrides.json),
    apoi fallback pe setarea din coefficients.
    """
    ui_type = (overrides.get("incalzire") or overrides.get("heating") or "").lower()
    if ui_type:
        return ui_type
    return (coeff.get("type") or "gaz").lower()


def main_single_plan() -> None:
    area_m2, area_raw = _get_house_area()
    coeff = _load_json(HEATING_COEFFS_JSON)
    overrides = _load_json(OFFER_OVERRIDES_JSON) if OFFER_OVERRIDES_JSON.exists() else {}
    energy_site = _load_json(ENERGY_SITE_COEFFS_JSON) if ENERGY_SITE_COEFFS_JSON.exists() else {}

    currency = coeff.get("currency", "EUR")

    base_coef = float(coeff["coefficient_heating_per_m2"])
    type_coeffs = coeff.get("type_coefficients", {})
    chosen_type = _get_heating_type(overrides, coeff)

    type_coef = float(type_coeffs.get(chosen_type, 1.0))

    # cost variabil = aria * base_coef * type_coef
    variable_cost = round(area_m2 * base_coef * type_coef, 2)

    fixed_map = energy_site.get("heating_fixed_costs", {})
    fixed_cost = float(fixed_map.get(chosen_type, 0.0))

    total = round(variable_cost + fixed_cost, 2)

    out = {
        "meta": {
            "component": "heating",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "currency": currency,
            "area_source": str(HOUSE_AREA_JSON.name),
        },
        "inputs": {
            "area_m2": round(area_m2, 2),
            "coefficient_heating_per_m2": base_coef,
            "type": chosen_type,
            "type_coefficient": type_coef,
            "fixed_cost_eur": fixed_cost,
        },
        "calculation": {
            "formula": "area_m2 * coefficient_heating_per_m2 * type_coefficient + fixed_cost",
            "variable_part_eur": variable_cost,
            "result": total,
        },
        "debug": {
            "house_area_raw": area_raw,
            "type_coefficients": type_coeffs,
        },
    }

    HEATING_OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(HEATING_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    record_json(
        HEATING_OUTPUT_JSON,
        stage="services",
        caption="Estimare cost încălzire (coef bază * tip + cost fix).",
    )

    print(f"✅ heating_from_area → {HEATING_OUTPUT_JSON} (total={total} {currency})")


if __name__ == "__main__":
    run_for_plans(main_single_plan)
