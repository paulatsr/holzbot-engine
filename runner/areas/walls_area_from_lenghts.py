# runner/areas/walls_area_from_lengths.py

import json
from pathlib import Path

from runner.utils.io import (
    WALLS_MEASUREMENTS_JSON,
    WALLS_AREA_FROM_LENGTHS_JSON,
)
from runner.config.settings import WALL_HEIGHTS_M
from runner.workers.plan_worker import run_for_plans
from runner.ui_export import record_json


def _load_walls_lengths(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Lipsește fișierul cu lungimile pereților: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_final_lengths(data: dict) -> tuple[float, float]:
    """
    Extrage lungimile finale interior/exterior din structura produsă de
    runner/geometry/walls_length_from_plan.py

    Ne așteptăm la ceva de genul:

    {
      "scale_meters_per_pixel": ...,
      "estimations": {
        "by_pixels": { "interior_meters": ..., "exterior_meters": ... },
        "by_proportion": { ... },
        "average_result": {
          "interior_meters": <float>,
          "exterior_meters": <float>
        }
      },
      "confidence": "...",
      "verification_notes": "..."
    }
    """
    estim = data.get("estimations") or {}
    avg = estim.get("average_result") or {}

    interior = avg.get("interior_meters")
    exterior = avg.get("exterior_meters")

    # fallback-uri, în caz că lipsește average_result
    if interior is None or exterior is None:
        by_pixels = estim.get("by_pixels") or {}
        by_prop = estim.get("by_proportion") or {}
        # ia media dintre cele două metode, unde există
        def _avg(a, b):
            vals = [v for v in (a, b) if v is not None]
            return sum(vals) / len(vals) if vals else None

        interior = interior or _avg(
            by_pixels.get("interior_meters"),
            by_prop.get("interior_meters"),
        )
        exterior = exterior or _avg(
            by_pixels.get("exterior_meters"),
            by_prop.get("exterior_meters"),
        )

    if interior is None or exterior is None:
        raise ValueError(
            "Nu am putut determina lungimile finale interior/exterior din JSON."
        )

    return float(interior), float(exterior)


def main_single_plan() -> None:
    data = _load_walls_lengths(WALLS_MEASUREMENTS_JSON)
    interior_len_m, exterior_len_m = _get_final_lengths(data)

    h_int = float(WALL_HEIGHTS_M.get("interior_wall", 2.6))
    h_ext = float(WALL_HEIGHTS_M.get("exterior_wall", 2.8))

    interior_area_m2 = interior_len_m * h_int
    exterior_area_m2 = exterior_len_m * h_ext
    total_area_m2 = interior_area_m2 + exterior_area_m2

    result = {
        "source_file": WALLS_MEASUREMENTS_JSON.name,
        "wall_heights_m": {
            "interior_wall": h_int,
            "exterior_wall": h_ext,
        },
        "walls_lengths_m": {
            "interior_meters": round(interior_len_m, 3),
            "exterior_meters": round(exterior_len_m, 3),
        },
        "walls_area_m2": {
            "interior_area_m2": round(interior_area_m2, 2),
            "exterior_area_m2": round(exterior_area_m2, 2),
            "total_area_m2": round(total_area_m2, 2),
        },
    }

    WALLS_AREA_FROM_LENGTHS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(WALLS_AREA_FROM_LENGTHS_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    record_json(
        WALLS_AREA_FROM_LENGTHS_JSON,
        stage="area",
        caption="Aria pereților (interior/exterior) din lungimi * înălțime.",
    )

    print(f"✅ walls_area_from_lengths → {WALLS_AREA_FROM_LENGTHS_JSON}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run_for_plans(main_single_plan)
