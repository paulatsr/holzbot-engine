# area/price_summary_full.py
import json
from pathlib import Path
from datetime import datetime
import math
import os

# ===================== FILES =====================
house_area_file         = Path("area/house_area_gemini.json")
walls_area_file         = Path("area/wall_areas_from_gemini.json")
openings_all_file       = Path("perimeter/openings_all.json")
roof_price_file         = Path("roof/roof_price_estimation.json")
output_file             = Path("area/price_summary_full.json")

# new configs / overrides
offer_overrides_file    = Path("area/offer_overrides.json")
system_prefab_file      = Path("area/system_prefab_coeffs.json")
foundation_coeff_file   = Path("area/foundation_coefficients.json")
finish_coeffs_file      = Path("area/finish_coefficients.json")
openings_prices_file    = Path("openings/openings_prices.json")
energy_site_file        = Path("area/energy_site_coefficients.json")

# services
electricity_coeff_file  = Path("electricity/electricity_coefficients.json")
sewage_coeff_file       = Path("sewage/sewage_coefficients.json")
heating_coeff_file      = Path("heating/heating_coefficients.json")

# outputs (services / aux)
electricity_output      = Path("electricity/output_electricity.json")
sewage_output           = Path("sewage/output_sewage.json")
heating_output          = Path("heating/output_heating.json")
floor_ceiling_output    = Path("area/floor_ceiling_price.json")

# legacy/other area coeffs (for floors/ceilings counts etc)
area_coefficients_file  = Path("area/area_coefficients.json")
basement_config_file    = Path("basement/basement_config.json")
offer_coefficients_file = Path("area/offer_coefficients.json")

# ===================== HELPERS =====================
def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"❌ Lipsă fișier: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def dump_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

def get_house_area() -> float:
    if area_coefficients_file.exists():
        try:
            cfg = load_json(area_coefficients_file)
            if cfg.get("house_area_m2") is not None:
                return float(cfg["house_area_m2"])
        except Exception:
            pass
    data = load_json(house_area_file)
    return float(data["surface_estimation"]["final_area_m2"])

def main_single_plan():
    # ===================== LOAD BASES =====================
    area_house = get_house_area()
    walls_data = load_json(walls_area_file)
    interior_walls_area_gross = float(walls_data["computed_areas"]["interior_walls_area_m2"])
    exterior_walls_area_gross = float(walls_data["computed_areas"]["exterior_walls_area_m2"])

    openings = load_json(openings_all_file)
    roof_data = load_json(roof_price_file)

    # roof components (support old/new)
    roof_base_avg = roof_sheet_metal = roof_extra_walls = roof_insulation = 0.0
    roof_total_final = None
    if "roof_final_total_eur" in roof_data and "components" in roof_data:
        comps = roof_data["components"]
        roof_base_avg   = float(comps["roof_base"]["average_total_eur"])
        roof_sheet_metal= float(comps.get("sheet_metal", {}).get("total_eur", 0.0))
        roof_extra_walls= float(comps.get("extra_walls", {}).get("total_eur", 0.0))
        roof_insulation = float(comps.get("insulation", {}).get("total_eur", 0.0))
        roof_total_final= float(roof_data["roof_final_total_eur"])
    else:
        roof_base_avg = float(roof_data["price_estimation"]["average_total_eur"])

    # overrides/configs
    overrides = load_json(offer_overrides_file) if offer_overrides_file.exists() else {}
    system_prefab = load_json(system_prefab_file)
    foundation_cfg= load_json(foundation_coeff_file)
    finishes_cfg  = load_json(finish_coeffs_file)
    openings_cfg  = load_json(openings_prices_file)
    energy_site   = load_json(energy_site_file)

    # area coeffs (floors/ceilings)
    acfg = load_json(area_coefficients_file) if area_coefficients_file.exists() else {
        "currency":"EUR","floors_count":1,"foundation_price_per_m2":0,"floor_coefficient_per_m2":0,"ceiling_coefficient_per_m2":0
    }
    floors_count = int(acfg.get("floors_count", 1))
    floor_coef   = float(acfg.get("floor_coefficient_per_m2", 0.0))
    ceil_coef    = float(acfg.get("ceiling_coefficient_per_m2", 0.0))

    # ===================== PARAMETERS FROM UI =====================
    tip_sistem        = overrides.get("tipSistem") or "Holzrahmen"
    grad_prefab       = overrides.get("gradPrefabricare") or "Panouri"
    tip_fundatie      = overrides.get("tipFundatie") or "Placă"
    fin_int_sel       = overrides.get("tipFinisajInterior") or "Tencuială"
    fin_ext_sel       = overrides.get("tipFinisajExterior") or "Tencuială"
    tampl_sel         = overrides.get("tipTamplarie") or "PVC"
    teren_tip         = overrides.get("terenTip") or "Plan"
    acces_santier     = overrides.get("accesSantier") or "Ușor"
    nivel_energetic   = overrides.get("nivelEnergetic") or "Standard"
    incalzire_sel     = overrides.get("incalzire") or "Gaz"

    # ===================== UNIT PRICES (STRUCTURE) =====================
    base_units = system_prefab["base_unit_prices_per_m2"].get(tip_sistem, system_prefab["base_unit_prices_per_m2"]["Holzrahmen"])
    pref_mult  = float(system_prefab["prefabrication_multipliers"].get(grad_prefab, 1.0))

    price_wall_int = float(base_units["interior"]) * pref_mult
    price_wall_ext = float(base_units["exterior"]) * pref_mult

    # ===================== FOUNDATION =====================
    fund_unit = float(foundation_cfg["unit_price_per_m2"].get(tip_fundatie, 0.0))
    foundation_cost = round(area_house * fund_unit, 2)

    # ===================== FLOORS/CEILING =====================
    floors_cost  = round(area_house * floor_coef * floors_count, 2)
    ceiling_cost = round(area_house * ceil_coef  * floors_count, 2)
    floor_final  = round(foundation_cost + floors_cost, 2)

    # ===================== OPENINGS & FINISHES =====================
    AREA_THRESHOLD_WINDOW = 2.5
    unit_win = float(openings_cfg["unit_price_per_m2"].get(tampl_sel, 450.0))
    unit_int_door = float(openings_cfg.get("interior_door_unit_price_per_m2", 450.0))

    fin_int_unit = float(finishes_cfg["interior"].get(fin_int_sel, 25.0))
    fin_ext_unit = float(finishes_cfg["exterior"].get(fin_ext_sel, 35.0))

    windows_details, doors_int_details, doors_ext_details = [], [], []
    subtract_area_interior = subtract_area_exterior = 0.0
    cost_windows = cost_doors_int = cost_doors_ext = 0.0

    for o in openings:
        typ = str(o.get("type","")).lower()
        status = str(o.get("status","")).lower()
        try:
            width = float(o["width_m"])
        except Exception:
            continue

        if "window" in typ:
            height = 1.25
        elif "door" in typ:
            height = 2.05
        else:
            continue

        area = width * height
        if not status:
            status = "exterior" if "window" in typ else "exterior"

        if "window" in typ:
            if area < AREA_THRESHOLD_WINDOW:
                unit = price_wall_int if status=="interior" else price_wall_ext
                cost = area * unit
                windows_details.append({"area_m2": round(area,3), "treated":"as_wall", "unit_eur_m2": unit, "cost_eur": round(cost,2)})
                if status=="interior": subtract_area_interior += area
                else: subtract_area_exterior += area
            else:
                cost = area * unit_win
                windows_details.append({"area_m2": round(area,3), "treated":"window", "unit_eur_m2": unit_win, "cost_eur": round(cost,2)})
                if status=="interior": subtract_area_interior += area
                else: subtract_area_exterior += area
            cost_windows += cost

        elif "door" in typ:
            if status == "interior":
                unit = unit_int_door
                cost = area * unit
                doors_int_details.append({"area_m2": round(area,3), "unit_eur_m2": unit, "cost_eur": round(cost,2)})
                subtract_area_interior += area
                cost_doors_int += cost
            else:
                unit = unit_win     # exterior doors use same frame system unit
                cost = area * unit
                doors_ext_details.append({"area_m2": round(area,3), "unit_eur_m2": unit, "cost_eur": round(cost,2)})
                subtract_area_exterior += area
                cost_doors_ext += cost

    # net wall areas
    interior_walls_area_net = max(0.0, interior_walls_area_gross - subtract_area_interior)
    exterior_walls_area_net = max(0.0, exterior_walls_area_gross - subtract_area_exterior)

    # structure costs by dynamic unit prices
    cost_walls_int_structure = round(interior_walls_area_net * price_wall_int, 2)
    cost_walls_ext_structure = round(exterior_walls_area_net * price_wall_ext, 2)

    # finishes
    interior_finish_total = round(interior_walls_area_net * fin_int_unit, 2)
    exterior_finish_total = round(exterior_walls_area_net * fin_ext_unit, 2)

    # ===================== SERVICES =====================
    def calc_electricity(area_m2: float):
        cfg = load_json(electricity_coeff_file)
        coef = float(cfg["coefficient_electricity_per_m2"])
        total = round(area_m2 * coef, 2)
        dump_json(electricity_output, {
            "meta":{"component":"electricity","generated_at":datetime.utcnow().isoformat()+"Z","currency":cfg.get("currency","EUR")},
            "inputs":{"area_m2":area_m2,"coefficient_electricity_per_m2":coef},
            "calculation":{"formula":"area_m2 * coefficient_electricity_per_m2","result":total}
        })
        return total

    def calc_sewage(area_m2: float):
        cfg = load_json(sewage_coeff_file)
        coef = float(cfg["coefficient_sewage_per_m2"])
        total = round(area_m2 * coef, 2)
        dump_json(sewage_output, {
            "meta":{"component":"sewage","generated_at":datetime.utcnow().isoformat()+"Z","currency":cfg.get("currency","EUR")},
            "inputs":{"area_m2":area_m2,"coefficient_sewage_per_m2":coef},
            "calculation":{"formula":"area_m2 * coefficient_sewage_per_m2","result":total}
        })
        return total

    def calc_heating(area_m2: float, chosen: str):
        cfg = load_json(heating_coeff_file)
        base_coef = float(cfg["coefficient_heating_per_m2"])
        type_coef = float(cfg.get("type_coefficients", {}).get(chosen, 1.0))
        per_m2 = round(area_m2 * base_coef * type_coef, 2)

        fixed_map = energy_site.get("heating_fixed_costs", {})
        fixed = float(fixed_map.get(chosen, 0.0))
        total = round(per_m2 + fixed, 2)

        dump_json(heating_output, {
            "meta":{"component":"heating","generated_at":datetime.utcnow().isoformat()+"Z","currency":cfg.get("currency","EUR")},
            "inputs":{"area_m2":area_m2,"coefficient_heating_per_m2":base_coef,"type":chosen,"type_coefficient":type_coef,"fixed_cost_eur":fixed},
            "calculation":{"formula":"area_m2 * base_coef * type_coef + fixed","result":total}
        })
        return total

    elec_total = canal_total = heat_total = 0.0
    try:
        elec_total  = calc_electricity(area_house)
        canal_total = calc_sewage(area_house)
        heat_total  = calc_heating(area_house, incalzire_sel)
    except FileNotFoundError as e:
        print(f"ℹ️ Servicii: {e}")

    # ===================== ROOF PARTS & STRUCTURE/HOUSE TOTALS =====================
    roof_structure_part = float(roof_base_avg) + float(roof_extra_walls)
    roof_house_extras   = float(roof_sheet_metal) + float(roof_insulation)

    final_struct = round(
        floor_final
        + roof_structure_part
        + cost_walls_int_structure
        + cost_walls_ext_structure
        + ceiling_cost,
        2
    )

    final_house_base = round(
        final_struct
        + roof_house_extras
        + cost_windows + cost_doors_int + cost_doors_ext
        + interior_finish_total + exterior_finish_total
        + elec_total + canal_total + heat_total,
        2
    )

    # ===================== ENERGY LEVEL MULTIPLIER =====================
    energy_mult = float(energy_site["energy_level_multipliers"].get(nivel_energetic, 1.0))
    final_house = round(final_house_base * energy_mult, 2)

    # ===================== MARKUPS (organization depends on terrain & access) =====================
    def load_offer_coeffs():
        try:
            cfg = load_json(offer_coefficients_file)
        except FileNotFoundError:
            cfg = {"organization_markup": 0.05, "supervising_markup": 0.03, "profit_margin": 0.10, "vat": 0.19, "currency": "EUR"}
        return {
            "organization_markup": float(cfg.get("organization_markup", 0.0)),
            "supervising_markup": float(cfg.get("supervising_markup", 0.0)),
            "profit_margin": float(cfg.get("profit_margin", 0.0)),
            "vat": float(cfg.get("vat", 0.0)),
            "currency": cfg.get("currency", "EUR")
        }

    offer = load_offer_coeffs()
    org_base   = offer["organization_markup"]
    access_mul = float(energy_site["site_access_multipliers_for_org"].get(acces_santier, 1.0))
    terrain_mul= float(energy_site["terrain_multipliers_for_org"].get(teren_tip, 1.0))
    org_effective = round(org_base * access_mul * terrain_mul, 6)

    multiplier = 1.0 + org_effective + offer["supervising_markup"] + offer["profit_margin"]
    semi_value = round(final_house * multiplier, 2)
    final_offer = round(semi_value * (1.0 + offer["vat"]), 2)

    # ===================== LOGGING (very detailed) =====================
    print("\n===================== 📊 DATE INIȚIALE =====================")
    print(f"🏠 Suprafață casă (A): {area_house:.2f} m²")
    print(f"🧱 Pereți interiori BRUT: {interior_walls_area_gross:.2f} m² | exteriori BRUT: {exterior_walls_area_gross:.2f} m²")
    print("============================================================\n")

    print("========= 🧩 SISTEM & PREFAB =========")
    print(f"Tip sistem: {tip_sistem} | Unități bază: int={base_units['interior']} €/m², ext={base_units['exterior']} €/m²")
    print(f"Grad prefabricare: {grad_prefab} | multiplier prefabricare: {pref_mult}")
    print(f"→ Unități structură rezultate: int={price_wall_int:.2f} €/m², ext={price_wall_ext:.2f} €/m²\n")

    print("========= 🧱 PEREȚI + DESCHIDERI =========")
    print(f"Tamplărie: {tampl_sel} | unități ferestre/uşi ext: {unit_win} €/m² | uși interior: {unit_int_door} €/m²")
    print(f"Prag fereastră ca perete: {AREA_THRESHOLD_WINDOW} m²")
    print(f"Area scăzută din pereți prin deschideri (se actualizează în bucla): interior/exterior…")
    print(f"→ După parcurgere: A_int_net={interior_walls_area_net:.2f} m², A_ext_net={exterior_walls_area_net:.2f} m²")
    print(f"Cost structură pereți: int = A_int_net×{price_wall_int} = €{cost_walls_int_structure:.2f}; ext = A_ext_net×{price_wall_ext} = €{cost_walls_ext_structure:.2f}")
    print(f"Ferestre total: €{cost_windows:.2f} | Uși int: €{cost_doors_int:.2f} | Uși ext: €{cost_doors_ext:.2f}\n")

    print("========= 🎨 FINISAJE =========")
    print(f"Interior: {fin_int_sel} @ {fin_int_unit} €/m² → €{interior_finish_total:.2f}")
    print(f"Exterior: {fin_ext_sel} @ {fin_ext_unit} €/m² → €{exterior_finish_total:.2f}\n")

    print("========= 🏗 FUNDAȚIE / PODEA / TAVAN =========")
    print(f"Fundație: {tip_fundatie} @ {fund_unit} €/m² → A×unit = {area_house:.2f}×{fund_unit} = €{foundation_cost:.2f}")
    print(f"Podele: A×coef×etaje = {area_house:.2f}×{floor_coef}×{floors_count} = €{floors_cost:.2f}")
    print(f"Tavan:   A×coef×etaje = {area_house:.2f}×{ceil_coef}×{floors_count} = €{ceiling_cost:.2f}")
    print(f"→ Floor final (fundatie+etaje): €{floor_final:.2f}\n")

    print("========= 🏠 ACOPERIȘ =========")
    print(f"Roof base avg: €{roof_base_avg:.2f} | extra_walls: €{roof_extra_walls:.2f} | sheet_metal: €{roof_sheet_metal:.2f} | insulation: €{roof_insulation:.2f}")
    print(f"→ roof_structure_part = base + extra = €{roof_structure_part:.2f}")
    print(f"→ roof_house_extras   = sheet + insulation = €{roof_house_extras:.2f}\n")

    print("========= ⚡ SERVICII =========")
    print(f"Electricitate total: €{elec_total:.2f}")
    print(f"Canalizare total:    €{canal_total:.2f}")
    print(f"Încălzire ({incalzire_sel}):    €{heat_total:.2f}\n")

    print("========= 🧮 AGREGAȚI =========")
    print(f"PREȚ FINAL STRUCTURĂ = floor_final + roof_structure + walls_int + walls_ext + ceiling =")
    print(f"  = {floor_final:.2f} + {roof_structure_part:.2f} + {cost_walls_int_structure:.2f} + {cost_walls_ext_structure:.2f} + {ceiling_cost:.2f}")
    print(f"  = €{final_struct:.2f}")
    print(f"CASĂ (înainte de energie) = struct + roof_extras + fer/usi + finisaje + servicii =")
    print(f"  = {final_struct:.2f} + {roof_house_extras:.2f} + {(cost_windows + cost_doors_int + cost_doors_ext):.2f} + {(interior_finish_total + exterior_finish_total):.2f} + {(elec_total + canal_total + heat_total):.2f}")
    print(f"  = €{final_house_base:.2f}")
    print(f"Nivel energetic: {nivel_energetic} → multiplier {energy_mult} ⇒ CASĂ = €{final_house:.2f}\n")

    print("========= 🏗️ ORGANIZARE ȘANTIER & OFERTARE =========")
    print(f"Acces: {acces_santier} → mul_access={access_mul} | Teren: {teren_tip} → mul_teren={terrain_mul}")
    print(f"Org. base={org_base:.4f} ⇒ org_effective = base×mul_access×mul_teren = {org_base:.4f}×{access_mul}×{terrain_mul} = {org_effective:.4f}")
    print(f"Multiplicator ofertă = 1 + org_eff + supervising({offer['supervising_markup']:.4f}) + profit({offer['profit_margin']:.4f}) = {multiplier:.4f}")
    print(f"VALOARE SEMIFINALĂ = CASĂ×mult = {final_house:.2f}×{multiplier:.4f} = €{semi_value:.2f}")
    print(f"TVA={offer['vat']*100:.1f}% ⇒ OFERTĂ FINALĂ = €{final_offer:.2f}")
    print("=====================================================\n")

    # ===================== JSON OUTPUT =====================
    result = {
        "meta": {"generated_at": datetime.utcnow().isoformat()+"Z","currency":"EUR"},
        "inputs": {
            "area_house_m2": round(area_house,2),
            "system": tip_sistem,
            "prefabrication": grad_prefab,
            "foundation_type": tip_fundatie,
            "finish_interior": fin_int_sel,
            "finish_exterior": fin_ext_sel,
            "joinery_type": tampl_sel,
            "terrain": teren_tip,
            "site_access": acces_santier,
            "energy_level": nivel_energetic,
            "heating": incalzire_sel
        },
        "unit_prices": {
            "walls_structure_interiors_eur_m2": round(price_wall_int,2),
            "walls_structure_exteriors_eur_m2": round(price_wall_ext,2),
            "foundation_eur_m2": fund_unit,
            "finishes_interior_eur_m2": fin_int_unit,
            "finishes_exterior_eur_m2": fin_ext_unit,
            "windows_doors_ext_eur_m2": unit_win,
            "interior_door_eur_m2": unit_int_door
        },
        "roof_breakdown": {
            "roof_base_avg_eur": roof_base_avg,
            "sheet_metal_eur": roof_sheet_metal,
            "extra_walls_eur": roof_extra_walls,
            "insulation_eur": roof_insulation,
            "roof_final_total_eur": roof_total_final if roof_total_final is not None else round(roof_base_avg + roof_sheet_metal + roof_extra_walls + roof_insulation, 2)
        },
        "components": {
            "walls_structure": {
                "interior": {"net_area_m2": round(interior_walls_area_net,2), "unit_price_eur_per_m2": round(price_wall_int,2), "cost_eur": round(cost_walls_int_structure,2)},
                "exterior": {"net_area_m2": round(exterior_walls_area_net,2), "unit_price_eur_per_m2": round(price_wall_ext,2), "cost_eur": round(cost_walls_ext_structure,2)}
            },
            "finishes": {
                "interior": {"unit_price_eur_per_m2": fin_int_unit, "cost_eur": interior_finish_total},
                "exterior": {"unit_price_eur_per_m2": fin_ext_unit, "cost_eur": exterior_finish_total}
            },
            "openings": {
                "windows_total_eur": round(cost_windows,2),
                "doors_interior_total_eur": round(cost_doors_int,2),
                "doors_exterior_total_eur": round(cost_doors_ext,2)
            },
            "floor_system": {"foundation_cost_eur": foundation_cost, "floors_cost_eur": floors_cost, "total_floor_eur": floor_final},
            "ceiling_system": {"total_ceiling_eur": ceiling_cost},
            "services": {"electricity_total_eur": elec_total, "sewage_total_eur": canal_total, "heating_total_eur": heat_total}
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
                "organization_base": offer["organization_markup"],
                "supervising": offer["supervising_markup"],
                "profit": offer["profit_margin"],
                "vat": offer["vat"]
            }
        }
    }

    dump_json(output_file, result)
    print(f"✅ Rezumat complet salvat în {output_file}")

    dump_json(
        floor_ceiling_output,
        {
            "meta": {"generated_at": datetime.utcnow().isoformat() + "Z"},
            "inputs": {
                "house_area_m2": round(area_house, 2),
                "floors_count": floors_count,
                "floor_coefficient_per_m2": floor_coef,
                "ceiling_coefficient_per_m2": ceil_coef,
                "foundation_unit_eur_m2": fund_unit,
                "foundation_type": tip_fundatie
            },
            "results": {
                "foundation_total_eur": foundation_cost,
                "floor_total_eur": floor_final,
                "ceiling_total_eur": ceiling_cost
            }
        }
    )
    print(f"📝 Output podea+tavan salvat în {floor_ceiling_output}")


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
