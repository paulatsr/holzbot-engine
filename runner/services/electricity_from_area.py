# runner/services/electricity_from_area.py

import json
from datetime import datetime

from runner.core.paths import (
    HOUSE_AREA_JSON,
    ELECTRICITY_COEFFS_JSON,
    ELECTRICITY_OUTPUT_JSON,
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


def _get_coefficients() -> dict:
    return _load_json(ELECTRICITY_COEFFS_JSON)


def main_single_plan() -> None:
    area_m2, area_raw = _get_house_area()
    coeff = _get_coefficients()

    coef_el = float(coeff["coefficient_electricity_per_m2"])
    currency = coeff.get("currency", "EUR")

    total = round(area_m2 * coef_el, 2)

    out = {
        "meta": {
            "component": "electricity",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "currency": currency,
            "area_source": str(HOUSE_AREA_JSON.name),
        },
        "inputs": {
            "area_m2": round(area_m2, 2),
            "coefficient_electricity_per_m2": coef_el,
        },
        "calculation": {
            "formula": "area_m2 * coefficient_electricity_per_m2",
            "result": total,
        },
        "debug": {
            "house_area_raw": area_raw,
        },
    }

    ELECTRICITY_OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(ELECTRICITY_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    record_json(
        ELECTRICITY_OUTPUT_JSON,
        stage="services",
        caption="Estimare cost electricitate (coef * aria).",
    )

    print(f"✅ electricity_from_area → {ELECTRICITY_OUTPUT_JSON} (total={total} {currency})")


if __name__ == "__main__":
    run_for_plans(main_single_plan)
