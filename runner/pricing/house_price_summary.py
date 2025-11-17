# runner/pricing/house_price_summary.py

import json
from datetime import datetime

from runner.core.paths import (
    HOUSE_AREA_JSON,
    WALLS_AREA_WITH_OPENINGS_JSON,
    ROOF_PRICE_JSON,
    ELECTRICITY_OUTPUT_JSON,
    SEWAGE_OUTPUT_JSON,
    HEATING_OUTPUT_JSON,
    SYSTEM_PREFAB_COEFFS_JSON,
    FOUNDATION_COEFFS_JSON,
    FINISH_COEFFS_JSON,
    ENERGY_SITE_COEFFS_JSON,
    OFFER_OVERRIDES_JSON,
    OFFER_COEFFS_JSON,
    AREA_MISC_COEFFS_JSON,
    PRICE_SUMMARY_JSON,
    FLOOR_CEILING_OUTPUT_JSON,
    OPENINGS_PRICING_JSON,
)
from runner.core.multi_plan_runner import run_for_plans
from runner.ui_export import record_json


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_house_area() -> float:
    data = _load_json(HOUSE_AREA_JSON)
    val = float(
        data.get("surface_estimation", {}).get("final_area_m2")
        or data.get("area_m2")
        or 0.0
    )
    if val <= 0:
        raise ValueError(f"House area <= 0 în {HOUSE_AREA_JSON}")
    return val


def _get_walls_net_areas() -> tuple[float, float]:
    data = _load_json(WALLS_AREA_WITH_OPENINGS_JSON)
    net = data.get("walls_area_after_openings_m2") or {}
    int_net = float(net.get("interior_area_m2") or 0.0)
    ext_net = float(net.get("exterior_area_m2") or 0.0)
    return int_net, ext_net


def _safe_load(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    return _load_json(path)


def main_single_plan() -> None:
    # --- 1. Date de bază ---
    area_house = _get_house_area()
    walls_int_net_m2, walls_ext_net_m2 = _get_walls_net_areas()

    roof_data = _load_json(ROOF_PRICE_JSON)
    roof_total = float(
        roof_data.get("roof_final_total_eur")
        or roof_data.get("price_estimation", {}).get("average_total_eur")
        or 0.0
    )

    elec_data = _safe_load(ELECTRICITY_OUTPUT_JSON, {})
    sewage_data = _safe_load(SEWAGE_OUTPUT_JSON, {})
    heating_data = _safe_load(HEATING_OUTPUT_JSON, {})
    openings_price_data = _safe_load(OPENINGS_PRICING_JSON, {})

    elec_total = float(elec_data.get("calculation", {}).get("result") or 0.0)
    sewage_total = float(sewage_data.get("calculation", {}).get("result") or 0.0)
    heating_total = float(heating_data.get("calculation", {}).get("result") or 0.0)
    openings_total = float(
        openings_price_data.get("summary", {}).get("total_openings_price_eur") or 0.0
    )

    # --- 2. Config / coeficienți ---
    system_prefab = _load_json(SYSTEM_PREFAB_COEFFS_JSON)
    foundation_cfg = _load_json(FOUNDATION_COEFFS_JSON)
    finish_cfg = _load_json(FINISH_COEFFS_JSON)
    energy_site = _safe_load(ENERGY_SITE_COEFFS_JSON, {})
    overrides = _safe_load(OFFER_OVERRIDES_JSON, {})
    offer_cfg = _safe_load(OFFER_COEFFS_JSON, {})
    area_misc = _safe_load(AREA_MISC_COEFFS_JSON, {})

    # UI parameters (cu fallback-uri decente)
    tip_sistem = overrides.get("tipSistem") or "Holzrahmen"
    grad_prefab = overrides.get("gradPrefabricare") or "Panouri"
    tip_fundatie = overrides.get("tipFundatie") or "Placă"
    fin_int_sel = overrides.get("tipFinisajInterior") or "Tencuială"
    fin_ext_sel = overrides.get("tipFinisajExterior") or "Tencuială"
    teren_tip = overrides.get("terenTip") or "Plan"
    acces_santier = overrides.get("accesSantier") or "Ușor"
    nivel_energetic = overrides.get("nivelEnergetic") or "Standard"

    floors_count = int(area_misc.get("floors_count", 1))
    floor_coef = float(area_misc.get("floor_coefficient_per_m2", 0.0))
    ceil_coef = float(area_misc.get("ceiling_coefficient_per_m2", 0.0))

    # --- 3. Unit prices structură ---
    base_units = system_prefab["base_unit_prices_per_m2"].get(
        tip_sistem, system_prefab["base_unit_prices_per_m2"]["Holzrahmen"]
    )
    pref_mult = float(system_prefab["prefabrication_multipliers"].get(grad_prefab, 1.0))

    price_wall_int = float(base_units["interior"]) * pref_mult
    price_wall_ext = float(base_units["exterior"]) * pref_mult

    # fundație
    fund_unit = float(foundation_cfg["unit_price_per_m2"].get(tip_fundatie, 0.0))
    foundation_cost = round(area_house * fund_unit, 2)

    # podea / tavan
    floors_cost = round(area_house * floor_coef * floors_count, 2)
    ceiling_cost = round(area_house * ceil_coef * floors_count, 2)
    floor_final = round(foundation_cost + floors_cost, 2)

    # pereți structură
    cost_walls_int_struct = round(walls_int_net_m2 * price_wall_int, 2)
    cost_walls_ext_struct = round(walls_ext_net_m2 * price_wall_ext, 2)

    # --- 4. Finisaje ---
    fin_int_unit = float(finish_cfg["interior"].get(fin_int_sel, 25.0))
    fin_ext_unit = float(finish_cfg["exterior"].get(fin_ext_sel, 35.0))

    interior_finish_total = round(walls_int_net_m2 * fin_int_unit, 2)
    exterior_finish_total = round(walls_ext_net_m2 * fin_ext_unit, 2)

    # --- 5. Structură + casă înainte de energie ---
    final_struct = round(
        floor_final
        + cost_walls_int_struct
        + cost_walls_ext_struct
        + ceiling_cost,
        2,
    )

    final_house_base = round(
        final_struct
        + roof_total
        + interior_finish_total
        + exterior_finish_total
        + elec_total
        + sewage_total
        + heating_total
        + openings_total,  # <--- GOLURI
        2,
    )

    # --- 6. Nivel energetic ---
    energy_mult = float(
        energy_site.get("energy_level_multipliers", {}).get(nivel_energetic, 1.0)
    )
    final_house = round(final_house_base * energy_mult, 2)

    # --- 7. Markup & TVA ---
    org_base = float(offer_cfg.get("organization_markup", 0.05))
    supervising = float(offer_cfg.get("supervising_markup", 0.03))
    profit = float(offer_cfg.get("profit_margin", 0.10))
    vat = float(offer_cfg.get("vat", 0.19))
    currency = offer_cfg.get("currency", "EUR")

    access_mul = float(
        energy_site.get("site_access_multipliers_for_org", {}).get(acces_santier, 1.0)
    )
    terrain_mul = float(
        energy_site.get("terrain_multipliers_for_org", {}).get(teren_tip, 1.0)
    )

    org_effective = round(org_base * access_mul * terrain_mul, 6)
    multiplier = 1.0 + org_effective + supervising + profit

    semi_value = round(final_house * multiplier, 2)
    final_offer = round(semi_value * (1.0 + vat), 2)

    # --- 8. JSON output ---
    result = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "currency": currency,
        },
        "inputs": {
            "area_house_m2": round(area_house, 2),
            "walls_net_area_m2": {
                "interior": round(walls_int_net_m2, 2),
                "exterior": round(walls_ext_net_m2, 2),
            },
            "system": tip_sistem,
            "prefabrication": grad_prefab,
            "foundation_type": tip_fundatie,
            "finish_interior": fin_int_sel,
            "finish_exterior": fin_ext_sel,
            "terrain": teren_tip,
            "site_access": acces_santier,
            "energy_level": nivel_energetic,
        },
        "unit_prices": {
            "walls_structure_interiors_eur_m2": round(price_wall_int, 2),
            "walls_structure_exteriors_eur_m2": round(price_wall_ext, 2),
            "foundation_eur_m2": fund_unit,
            "finishes_interior_eur_m2": fin_int_unit,
            "finishes_exterior_eur_m2": fin_ext_unit,
        },
        "components": {
            "walls_structure": {
                "interior": {
                    "net_area_m2": round(walls_int_net_m2, 2),
                    "unit_price_eur_per_m2": round(price_wall_int, 2),
                    "cost_eur": cost_walls_int_struct,
                },
                "exterior": {
                    "net_area_m2": round(walls_ext_net_m2, 2),
                    "unit_price_eur_per_m2": round(price_wall_ext, 2),
                    "cost_eur": cost_walls_ext_struct,
                },
            },
            "finishes": {
                "interior": {
                    "unit_price_eur_per_m2": fin_int_unit,
                    "cost_eur": interior_finish_total,
                },
                "exterior": {
                    "unit_price_eur_per_m2": fin_ext_unit,
                    "cost_eur": exterior_finish_total,
                },
            },
            "floor_system": {
                "foundation_cost_eur": foundation_cost,
                "floors_cost_eur": floors_cost,
                "total_floor_eur": floor_final,
            },
            "ceiling_system": {
                "total_ceiling_eur": ceiling_cost,
            },
            "roof": {
                "roof_total_eur": roof_total,
            },
            "services": {
                "electricity_total_eur": elec_total,
                "sewage_total_eur": sewage_total,
                "heating_total_eur": heating_total,
            },
            "openings": {
                "pricing_file": str(OPENINGS_PRICING_JSON.name),
                "total_openings_price_eur": openings_total,
                "by_type": openings_price_data.get("types", {}),
            },
        },
        "summary": {
            "final_structure_eur": final_struct,
            "final_house_before_energy_eur": final_house_base,
            "energy_multiplier": energy_mult,
            "final_house_eur": final_house,
            "organizational_markup_effective": org_effective,
            "semi_value_eur": semi_value,
            "offer_final_eur": final_offer,
            "markups": {
                "organization_base": org_base,
                "supervising": supervising,
                "profit": profit,
                "vat": vat,
            },
        },
    }

    PRICE_SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(PRICE_SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # export separat floor/ceiling pentru UI
    floor_ceiling_payload = {
        "meta": {"generated_at": datetime.utcnow().isoformat() + "Z"},
        "inputs": {
            "house_area_m2": round(area_house, 2),
            "floors_count": floors_count,
            "floor_coefficient_per_m2": floor_coef,
            "ceiling_coefficient_per_m2": ceil_coef,
            "foundation_unit_eur_m2": fund_unit,
            "foundation_type": tip_fundatie,
        },
        "results": {
            "foundation_total_eur": foundation_cost,
            "floor_total_eur": floor_final,
            "ceiling_total_eur": ceiling_cost,
        },
    }
    with open(FLOOR_CEILING_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(floor_ceiling_payload, f, indent=2, ensure_ascii=False)

    record_json(
        PRICE_SUMMARY_JSON,
        stage="pricing",
        caption=(
            "Rezumat complet casă: structură + finisaje + acoperiș + servicii + "
            "goluri + markup."
        ),
    )
    record_json(
        FLOOR_CEILING_OUTPUT_JSON,
        stage="pricing",
        caption="Detaliu fundație / podea / tavan.",
    )

    print(f"✅ house_price_summary → {PRICE_SUMMARY_JSON}")
    print(f"   OFERTĂ FINALĂ: {final_offer:.2f} {currency}")


if __name__ == "__main__":
    run_for_plans(main_single_plan)
