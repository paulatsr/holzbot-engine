# runner/areas/walls_area_with_openings.py

import json
from pathlib import Path

from runner.core.paths import (
    WALLS_AREA_FROM_LENGTHS_JSON,
    WALLS_AREA_WITH_OPENINGS_JSON,
    OPENINGS_ALL_JSON,
)
from runner.core.multi_plan_runner import run_for_plans
from runner.ui_export import record_json


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Lipsește fișierul: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _compute_openings_areas(data: dict) -> dict:
    """
    Aștept:
    {
      "openings": [
        {
          "id": "...",
          "type": "window" | "door" | "other",
          "wall_side": "interior" | "exterior",
          "area_m2": <float>
        },
        ...
      ]
    }
    """
    openings = data.get("openings") or []

    interior = 0.0
    exterior = 0.0
    unknown = 0.0

    breakdown = []

    for op in openings:
        area = float(op.get("area_m2") or 0.0)
        side = (op.get("wall_side") or "").lower().strip()
        typ = (op.get("type") or "").lower().strip()
        oid = op.get("id") or ""

        if area <= 0:
            continue

        if side == "interior":
            interior += area
        elif side == "exterior":
            exterior += area
        else:
            unknown += area

        breakdown.append(
            {
                "id": oid,
                "type": typ or "unknown",
                "wall_side": side or "unknown",
                "area_m2": round(area, 3),
            }
        )

    return {
        "interior_openings_m2": round(interior, 2),
        "exterior_openings_m2": round(exterior, 2),
        "unknown_openings_m2": round(unknown, 2),
        "total_openings_m2": round(interior + exterior + unknown, 2),
        "breakdown": breakdown,
    }


def main_single_plan() -> None:
    # 1) aria pereților brută
    walls_area_data = _load_json(WALLS_AREA_FROM_LENGTHS_JSON)
    walls_area = (walls_area_data.get("walls_area_m2") or {})

    raw_int = float(walls_area.get("interior_area_m2") or 0.0)
    raw_ext = float(walls_area.get("exterior_area_m2") or 0.0)
    raw_total = float(walls_area.get("total_area_m2") or (raw_int + raw_ext))

    # 2) deschideri
    openings_data = _load_json(OPENINGS_ALL_JSON)
    openings_areas = _compute_openings_areas(openings_data)

    o_int = openings_areas["interior_openings_m2"]
    o_ext = openings_areas["exterior_openings_m2"]
    o_total = openings_areas["total_openings_m2"]

    # 3) scădem aria golurilor
    net_int = max(raw_int - o_int, 0.0)
    net_ext = max(raw_ext - o_ext, 0.0)
    net_total = max(raw_total - o_total, 0.0)

    # sanity check
    warnings: list[str] = []
    if o_total > raw_total:
        warnings.append(
            "Aria totală a deschiderilor depășește aria totală a pereților. "
            "Am clamp-uit la 0. Verifică input-ul."
        )

    result = {
        "source_files": {
            "walls_area_from_lengths": WALLS_AREA_FROM_LENGTHS_JSON.name,
            "openings_all": OPENINGS_ALL_JSON.name,
        },
        "walls_area_before_openings_m2": {
            "interior_area_m2": round(raw_int, 2),
            "exterior_area_m2": round(raw_ext, 2),
            "total_area_m2": round(raw_total, 2),
        },
        "openings_area_m2": {
            "interior_openings_m2": openings_areas["interior_openings_m2"],
            "exterior_openings_m2": openings_areas["exterior_openings_m2"],
            "unknown_openings_m2": openings_areas["unknown_openings_m2"],
            "total_openings_m2": openings_areas["total_openings_m2"],
        },
        "walls_area_after_openings_m2": {
            "interior_area_m2": round(net_int, 2),
            "exterior_area_m2": round(net_ext, 2),
            "total_area_m2": round(net_total, 2),
        },
        "openings_breakdown": openings_areas["breakdown"],
        "warnings": warnings,
    }

    WALLS_AREA_WITH_OPENINGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(WALLS_AREA_WITH_OPENINGS_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    record_json(
        WALLS_AREA_WITH_OPENINGS_JSON,
        stage="area",
        caption="Aria pereților după scăderea deschiderilor.",
    )

    print(f"✅ walls_area_with_openings → {WALLS_AREA_WITH_OPENINGS_JSON}")
    if warnings:
        print("\n⚠️  WARNINGS:")
        for w in warnings:
            print(" -", w)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run_for_plans(main_single_plan)
