# runner/openings/openings_pricing.py

import json
from collections import defaultdict
from datetime import datetime

from runner.utils.io import (
    OPENINGS_ALL_JSON,
    OPENINGS_COEFFS_JSON,
    OPENINGS_PRICING_JSON,
)
from runner.workers.plan_worker import run_for_plans
from runner.ui_export import record_json


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_opening_type(opening: dict) -> str:
    """
    Încearcă să ia un tip cât mai specific pentru pricing:
    - întâi 'pricing_type'
    - apoi 'type'
    - fallback 'window'
    """
    tp = (
        opening.get("pricing_type")
        or opening.get("type")
        or "window"
    )
    return str(tp).lower()


def _get_opening_area(opening: dict) -> float:
    """
    Ia direct 'area_m2' dacă există.
    Dacă nu, încearcă width_m * height_m.
    Altfel, 0.0.
    """
    if "area_m2" in opening:
        try:
            return float(opening["area_m2"])
        except (TypeError, ValueError):
            return 0.0

    w = opening.get("width_m")
    h = opening.get("height_m")
    try:
        if w is not None and h is not None:
            return float(w) * float(h)
    except (TypeError, ValueError):
        pass

    return 0.0


def _group_openings_by_type(openings: list[dict]) -> dict[str, dict]:
    """
    return:
    {
      "window": {
        "count": 10,
        "total_area_m2": 23.5
      },
      "door_exterior": {
        "count": 3,
        "total_area_m2": 7.2
      },
      ...
    }
    """
    agg: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_area_m2": 0.0})

    for op in openings:
        tp = _get_opening_type(op)
        area = _get_opening_area(op)
        if area <= 0:
            continue
        agg[tp]["count"] += 1
        agg[tp]["total_area_m2"] += area

    # rotunjim un pic ariile
    for tp, d in agg.items():
        d["total_area_m2"] = round(d["total_area_m2"], 3)

    return agg


def main_single_plan() -> None:
    # --- 1. Load data ---
    if not OPENINGS_ALL_JSON.exists():
        raise FileNotFoundError(f"Nu am găsit {OPENINGS_ALL_JSON}. Rulează întâi collect_openings_data.")

    openings_data = _load_json(OPENINGS_ALL_JSON)
    openings_list = openings_data.get("openings") or openings_data.get("items") or []

    if not isinstance(openings_list, list):
        raise ValueError(f"Structură neașteptată în {OPENINGS_ALL_JSON}: nu e listă la 'openings'/'items'.")

    coeffs = _load_json(OPENINGS_COEFFS_JSON)
    currency = coeffs.get("currency", "EUR")
    type_cfg = coeffs.get("types", {})
    default_cfg = coeffs.get("default", {})
    default_price_m2 = float(default_cfg.get("price_per_m2", 300.0))

    # --- 2. Group by type ---
    grouped = _group_openings_by_type(openings_list)

    # --- 3. Pricing pe tip ---
    types_out = {}
    total_price = 0.0
    total_area = 0.0
    total_count = 0

    for tp, stats in grouped.items():
        total_area_m2 = stats["total_area_m2"]
        count = stats["count"]

        cfg = type_cfg.get(tp, {})
        price_per_m2 = float(cfg.get("price_per_m2", default_price_m2))

        type_price = round(total_area_m2 * price_per_m2, 2)

        types_out[tp] = {
            "count": count,
            "total_area_m2": total_area_m2,
            "unit_price_eur_per_m2": price_per_m2,
            "total_price_eur": type_price,
        }

        total_price += type_price
        total_area += total_area_m2
        total_count += count

    total_price = round(total_price, 2)
    total_area = round(total_area, 3)

    # --- 4. Output JSON ---
    out = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "currency": currency,
        },
        "types": types_out,
        "summary": {
            "total_openings_count": total_count,
            "total_openings_area_m2": total_area,
            "total_openings_price_eur": total_price,
        },
        "debug": {
            "coefficients_file": str(OPENINGS_COEFFS_JSON.name),
            "default_price_per_m2": default_price_m2,
        },
    }

    OPENINGS_PRICING_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OPENINGS_PRICING_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    record_json(
        OPENINGS_PRICING_JSON,
        stage="openings",
        caption="Pricing ferestre/uși pe tip și suprafață.",
    )

    print(
        f"✅ openings_pricing → {OPENINGS_PRICING_JSON} "
        f"(total_openings_price={total_price} {currency})"
    )


if __name__ == "__main__":
    run_for_plans(main_single_plan)
