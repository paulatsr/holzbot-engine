from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = Path(os.getenv("RUNS_ROOT") or os.getenv("WORKDIR") or (PROJECT_ROOT / "runs")).expanduser().resolve()
RUN_ID = (os.getenv("RUN_ID") or "local").strip()
RUN_DIR = RUNS_ROOT / RUN_ID
RUN_DIR.mkdir(parents=True, exist_ok=True)

PLAN_IMAGE = Path(os.getenv("PLAN_IMAGE") or (PROJECT_ROOT / "plan.jpg")).expanduser().resolve()
METERS_PIXEL_DIR = PROJECT_ROOT / "meters_pixel"
SCALE_RESULT_JSON = METERS_PIXEL_DIR / "scale_result.json"
HOUSE_AREA_JSON = PROJECT_ROOT / "area/house_area_gemini.json"
PERIMETER_DIR = PROJECT_ROOT / "perimeter"
WALLS_MEASUREMENTS_JSON = PERIMETER_DIR / "walls_measurements_gemini.json"
WALLS_AREA_FROM_LENGTHS_JSON = PROJECT_ROOT / "area/wall_areas_from_gemini.json"
WALLS_AREA_WITH_OPENINGS_JSON = PROJECT_ROOT / "area/wall_areas_combined.json"
OPENINGS_ALL_JSON = PERIMETER_DIR / "openings_all.json"
OPENINGS_COEFFS_JSON = PROJECT_ROOT / "area/openings_coefficients.json"
OPENINGS_PRICING_JSON = PROJECT_ROOT / "perimeter/openings_pricing.json"
ROOF_PRICE_JSON = PROJECT_ROOT / "roof/roof_price_estimation.json"
ELECTRICITY_COEFFS_JSON = PROJECT_ROOT / "electricity/electricity_coefficients.json"
ELECTRICITY_OUTPUT_JSON = PROJECT_ROOT / "electricity/output_electricity.json"
SEWAGE_COEFFS_JSON = PROJECT_ROOT / "sewage/sewage_coefficients.json"
SEWAGE_OUTPUT_JSON = PROJECT_ROOT / "sewage/output_sewage.json"
HEATING_COEFFS_JSON = PROJECT_ROOT / "heating/heating_coefficients.json"
HEATING_OUTPUT_JSON = PROJECT_ROOT / "heating/output_heating.json"
ENERGY_SITE_COEFFS_JSON = PROJECT_ROOT / "area/energy_site_coefficients.json"
OFFER_OVERRIDES_JSON = PROJECT_ROOT / "area/offer_overrides.json"
OFFER_COEFFS_JSON = PROJECT_ROOT / "area/offer_coefficients.json"
SYSTEM_PREFAB_COEFFS_JSON = PROJECT_ROOT / "area/system_prefab_coeffs.json"
FOUNDATION_COEFFS_JSON = PROJECT_ROOT / "area/foundation_coefficients.json"
FINISH_COEFFS_JSON = PROJECT_ROOT / "area/finish_coefficients.json"
AREA_MISC_COEFFS_JSON = PROJECT_ROOT / "area/area_coefficients.json"
FLOOR_CEILING_OUTPUT_JSON = PROJECT_ROOT / "area/floor_ceiling_price.json"
PRICE_SUMMARY_JSON = PROJECT_ROOT / "area/price_summary_full.json"
ROOF_COEFFS_JSON = PROJECT_ROOT / "roof/roof_coefficients.json"
SYSTEM_SELECTED_JSON = PROJECT_ROOT / "area/system_selected.json"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(payload: Any, path: Path) -> Path:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path
