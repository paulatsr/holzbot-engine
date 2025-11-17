#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# house_pricing.py
# ======================================================
# Scriptul agregă toate costurile într-un rezumat „price_summary_full.json”.
# Versiunea asta:
#   - Afișează bannere mari la start și la final
#   - Marchează clar fiecare fișier citit/scris
#   - Loghează formulele și rezultatele intermediare
#   - Trimite în UI (dacă ui_export e disponibil) fluxul live
#   - ✅ CADRAN 8: Generează direct oferta PDF + upload/notify
#   - ✅ NOU: suportă MULTI-PLAN:
#       * caută house_area_gemini_p01.json, p02... (dacă PLAN_COUNT>1)
#       * sumează ariile / pereții / deschiderile din toate planurile
#       * fallback la fișierele vechi single-plan dacă nu există multi-plan
#       * 🔹 salvează și snapshot per-plan în "engine_plans"
# ======================================================

import json, os
from pathlib import Path
from datetime import datetime

def ts():
    from datetime import datetime as _dt
    return _dt.now().strftime("%H:%M:%S.%f")[:-3]

def trace(msg: str):
    print(f"[{ts()}] [TRACE house_pricing] {msg}", flush=True)

print("\n" + "="*70, flush=True)
print("🏗️  ENTER house_pricing.py — agreg costuri pentru ofertă (multi-plan ready)", flush=True)
print("="*70 + "\n", flush=True)

# -------- helpers I/O ----------
def load_json(p: Path):
    trace(f"LOAD JSON: {p}")
    if not p.exists():
        raise FileNotFoundError(f"❌ Lipsă fișier: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return data

def dump_json(p: Path, obj: dict):
    trace(f"WRITE JSON: {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

# streaming live către UI (dacă e disponibil)
# + acces opțional la begin_stage/finalize_stage ca să putem „desena” CADRAN 8 în UI
begin_stage = finalize_stage = None
try:
    from ui_export import record_text, record_json, begin_stage as _begin, finalize_stage as _finalize
    begin_stage, finalize_stage = _begin, _finalize
    def stream_text(msg: str):
        record_text(msg, stage="house_pricing", filename="_live.txt", append=True)
        trace(f"UI_STREAM text: {msg[:120]}{'...' if len(msg)>120 else ''}")
    def stream_json(path: Path):
        record_json(str(path), stage="house_pricing")
        trace(f"UI_STREAM json: {path}")
except Exception:
    def stream_text(msg: str):
        print(msg, flush=True)
    def stream_json(_):
        pass

PRJ = Path(__file__).resolve().parent

# -------- fișiere intrare/ieșire ----------
house_area_file   = PRJ / "area/house_area_gemini.json"
walls_area_file   = PRJ / "area/wall_areas_from_gemini.json"
openings_all_file = PRJ / "perimeter/openings_all.json"
roof_price_file   = PRJ / "roof/roof_price_estimation.json"
output_file       = PRJ / "area/price_summary_full.json"

electricity_coeff_file = PRJ / "electricity/electricity_coefficients.json"
sewage_coeff_file      = PRJ / "sewage/sewage_coefficients.json"
heating_coeff_file     = PRJ / "heating/heating_coefficients.json"

area_coefficients_file = PRJ / "area/area_coefficients.json"
floor_ceiling_output   = PRJ / "area/floor_ceiling_price.json"  # (not used directly, păstrat ca ref)

basement_config_file   = PRJ / "basement/basement_config.json"
wall_coefficients_file = PRJ / "area/wall_coefficients.json"
offer_coefficients_file= PRJ / "area/offer_coefficients.json"

structure_coeffs_file  = PRJ / "area/structure_coefficients.json"
system_selected_file   = PRJ / "area/system_selected.json"
foundation_coeffs_file = PRJ / "area/foundation_coefficients.json"

ventilation_coeffs_file= PRJ / "ventilation/ventilation_coefficients.json"

# -------- fallback-uri ----------
PRICE_PER_WALL_INT_FALLBACK = 140.0
PRICE_PER_WALL_EXT_FALLBACK = 240.0
PRICE_PER_WINDOW            = 900.0
PRICE_PER_DOOR_INT          = 450.0
PRICE_PER_DOOR_EXT          = 900.0
AREA_THRESHOLD_WINDOW       = 2.5

# -------- utilitare multi-plan ----------
def _plan_suffixes():
    """
    Returnează lista de sufixe pentru planuri:
      PLAN_COUNT=1 -> [""]
      PLAN_COUNT=3 -> ["_p01","_p02","_p03"]
    """
    try:
        count = int(os.getenv("PLAN_COUNT", "1"))
    except ValueError:
        count = 1
    if count <= 1:
        return [""]
    return [f"_p{idx:02d}" for idx in range(1, count+1)]

# -------- utilitare ----------
def get_house_area() -> float:
    """
    Aria totală a casei:
      1) dacă area_coefficients.json are 'house_area_m2', folosim override.
      2) altfel, căutăm:
           area/house_area_gemini_p01.json, p02, ... și SUMĂM final_area_m2.
      3) fallback la area/house_area_gemini.json (single-plan).
    """
    trace("get_house_area()")

    # 1) override din area_coefficients.json, dacă există
    try:
        cfg = load_json(area_coefficients_file)
        if cfg.get("house_area_m2") is not None:
            v = float(cfg["house_area_m2"])
            trace(f"house_area_m2 override din area_coefficients.json = {v}")
            return v
    except Exception as e:
        trace(f"house_area_m2 override nu e disponibil: {e}")

    # 2) multi-plan: house_area_gemini_pXX.json
    suffs = _plan_suffixes()
    areas = []
    used = []
    for s in suffs:
        p = PRJ / "area" / f"house_area_gemini{s}.json"
        if p.exists():
            d = load_json(p)
            a = float(d["surface_estimation"]["final_area_m2"])
            trace(f"house_area din {p.name} = {a}")
            areas.append(a)
            used.append(p.name)

    if areas:
        total = float(sum(areas))
        trace(f"house_area total (multi-plan, {len(areas)} fișiere: {used}) = {total}")
        return total

    # 3) fallback single-plan
    data = load_json(house_area_file)
    v = float(data["surface_estimation"]["final_area_m2"])
    trace(f"house_area din {house_area_file.name} = {v}")
    return v

def load_walls_areas():
    """
    Returnează (interior_walls_area_gross, exterior_walls_area_gross) cumulate
    peste toate planurile:
      - caută wall_areas_from_gemini_p01.json, p02...
      - dacă nu găsește, revine la wall_areas_from_gemini.json.
    """
    trace("load_walls_areas()")
    suffs = _plan_suffixes()
    total_int = 0.0
    total_ext = 0.0
    used = []

    for s in suffs:
        p = PRJ / "area" / f"wall_areas_from_gemini{s}.json"
        if p.exists():
            j = load_json(p)
            total_int += float(j["computed_areas"]["interior_walls_area_m2"])
            total_ext += float(j["computed_areas"]["exterior_walls_area_m2"])
            used.append(p.name)

    if used:
        trace(f"walls din multi-plan files {used} => int={total_int}, ext={total_ext}")
        return total_int, total_ext

    # fallback single-plan
    data = load_json(walls_area_file)
    total_int = float(data["computed_areas"]["interior_walls_area_m2"])
    total_ext = float(data["computed_areas"]["exterior_walls_area_m2"])
    trace(f"walls din {walls_area_file.name} => int={total_int}, ext={total_ext}")
    return total_int, total_ext

def load_openings_all():
    """
    Returnează lista COMPLETĂ de deschideri (uși+ferestre) pentru toate planurile:
      - concatenează perimeter/openings_all_p01.json, p02...
      - dacă nu există, folosește perimeter/openings_all.json.
    """
    trace("load_openings_all()")
    suffs = _plan_suffixes()
    all_items = []
    used = []

    for s in suffs:
        p = PRJ / "perimeter" / f"openings_all{s}.json"
        if p.exists():
            j = load_json(p)
            if isinstance(j, list):
                all_items.extend(j)
            else:
                trace(f"[WARN] openings_all{s}.json nu este listă, îl ignor parțial.")
            used.append(p.name)

    if used:
        trace(f"openings din multi-plan {used}: total_items={len(all_items)}")
        return all_items

    # fallback single-plan
    data = load_json(openings_all_file)
    trace(f"openings din {openings_all_file.name}: total_items={len(data)}")
    return data

def collect_per_plan_data():
    """
    Construiește o listă cu datele brute pe fiecare plan:
      - area/house_area_gemini_pXX.json
      - area/wall_areas_from_gemini_pXX.json
      - perimeter/openings_all_pXX.json
      - roof/roof_price_estimation_pXX.json (dacă există)
    Cheia rezultată va fi "engine_plans" în price_summary_full.json,
    astfel încât frontend-ul/backend-ul să poată vedea exact ce a venit
    din fiecare plan, nu doar suma.
    """
    trace("collect_per_plan_data()")
    plans = []
    suffs = _plan_suffixes()

    for idx, s in enumerate(suffs, start=1):
        plan_id = f"p{idx:02d}"
        plan = {
            "planIndex": idx,
            "planId": plan_id,
        }

        # house_area
        p_area = PRJ / "area" / f"house_area_gemini{s}.json"
        if p_area.exists():
            plan["house_area"] = load_json(p_area)

        # wall_areas
        p_walls = PRJ / "area" / f"wall_areas_from_gemini{s}.json"
        if p_walls.exists():
            plan["wall_areas"] = load_json(p_walls)

        # openings
        p_open = PRJ / "perimeter" / f"openings_all{s}.json"
        if p_open.exists():
            plan["openings"] = load_json(p_open)

        # roof (dacă scriptul de roof scrie per-plan)
        p_roof = PRJ / "roof" / f"roof_price_estimation{s}.json"
        if p_roof.exists():
            plan["roof_price"] = load_json(p_roof)

        plans.append(plan)

    trace(f"collect_per_plan_data => {len(plans)} planuri")
    return plans

def _read_system_selection():
    trace("_read_system_selection()")
    tip = grad = fund = nivel = None
    ventil = False
    util = {"curent": True, "apa": True}
    nivelE = ""
    acces = ""
    teren = ""
    if system_selected_file.exists():
        j = load_json(system_selected_file)
        tip   = (j.get("tipSistem") or "").strip()
        grad  = (j.get("gradPrefabricare") or "").strip()
        fund  = (j.get("tipFundatie") or "").strip()
        nivel = (j.get("nivelOferta") or "").strip()
        ventil= bool(j.get("ventilatie_recuperare", False))
        util  = j.get("utilitati_site") or util
        nivelE= (j.get("nivelEnergetic") or "").strip()
        acces = (j.get("accesSantier") or "").strip()
        teren = (j.get("teren") or "").strip()
    trace(f"SYSTEM sel: tip={tip}, grad={grad}, fundatie={fund}, nivel={nivel}, ventil={ventil}, util={util}, energetic={nivelE}, acces={acces}, teren={teren}")
    return tip, grad, fund, nivel, ventil, util, nivelE, acces, teren

def _normalize_tip_sistem(s: str) -> str | None:
    k = (s or "").strip().upper().replace(" ", "")
    if not k: return None
    if k in ("CLT",): return "CLT"
    if k in ("HOLZRAHMEN","HOLZRAHMENBAU"): return "HOLZRAHMEN"
    if k in ("MASSIVHOLZ","MASSIV","LEMNMASIV"): return "MASSIVHOLZ"
    return None

def _normalize_prefab(s: str) -> str | None:
    k = (s or "").strip().upper()
    if not k: return None
    if "MODULE" in k: return "MODULE"
    if "PANOUR" in k: return "PANOURI"
    if "ȘANTIER" in k or "SANTIER" in k or "MONTAJ" in k: return "SANTIER"
    return None

def _normalize_fundatie(s: str) -> str | None:
    k = (s or "").strip().upper()
    if not k: return None
    if "PLAC" in k: return "PLACA"
    if "PILOT" in k: return "PILOTI"
    if "SOCLU" in k or "FUNDATIE CONTINUA" in k: return "SOCLU"
    return None

def resolve_wall_unit_prices():
    trace("resolve_wall_unit_prices()")
    debug = {"base_used": None, "modifier_used": None}
    tip_raw, grad_raw, *_ = _read_system_selection()
    tip  = _normalize_tip_sistem(tip_raw)
    grad = _normalize_prefab(grad_raw)
    base_int = PRICE_PER_WALL_INT_FALLBACK
    base_ext = PRICE_PER_WALL_EXT_FALLBACK
    modifier = 1.0
    try:
        cfg = load_json(structure_coeffs_file)
        bases = (cfg.get("base_unit_prices") or {})
        mods  = (cfg.get("prefabrication_modifiers") or {})
        if tip and tip in bases:
            base = bases[tip]
            base_int = float(base.get("interior", base_int))
            base_ext = float(base.get("exterior", base_ext))
            debug["base_used"] = {"system": tip, "interior": base_int, "exterior": base_ext}
        if grad and grad in mods:
            modifier = float(mods[grad])
            debug["modifier_used"] = {"prefab": grad, "value": modifier}
    except FileNotFoundError:
        trace("structure_coefficients.json lipsește, folosesc fallback-uri")
    trace(f"unit prices -> int={base_int} ext={base_ext} * modifier={modifier}")
    return base_int * modifier, base_ext * modifier, debug

def resolve_foundation_unit(area_fallback_unit: float):
    trace("resolve_foundation_unit()")
    tip_raw = _read_system_selection()[2]
    tip_key = _normalize_fundatie(tip_raw or "")
    debug = {"tipFundatie_raw": tip_raw or "", "tipFundatie_key": tip_key or "FALLBACK"}
    unit = float(area_fallback_unit)
    try:
        cfg = load_json(foundation_coeffs_file)
        units = (cfg.get("unit_prices") or {})
        if tip_key and tip_key in units:
            unit = float(units[tip_key])
            debug["unit_used"] = {"type": tip_key, "value": unit}
        else:
            debug["unit_used"] = {"type": "FALLBACK", "value": unit}
    except FileNotFoundError:
        debug["unit_used"] = {"type": "FALLBACK_NO_FILE", "value": unit}
    trace(f"foundation unit => {unit} ({debug['unit_used']})")
    return unit, debug

def load_area_coeffs(house_area: float):
    trace("load_area_coeffs()")
    cfg = load_json(area_coefficients_file)
    floors_count = int(cfg.get("floors_count", 1))
    foundation_price_per_m2 = float(cfg.get("foundation_price_per_m2", 0.0))
    floor_coefficient_per_m2 = float(cfg.get("floor_coefficient_per_m2", 0.0))
    ceiling_coefficient_per_m2 = float(cfg.get("ceiling_coefficient_per_m2", 0.0))
    area_override = cfg.get("house_area_m2")
    area_used = float(area_override) if area_override is not None else house_area
    trace(f"area_used={area_used}, floors_count={floors_count}, foundation_unit={foundation_price_per_m2}, floor_coef={floor_coefficient_per_m2}, ceiling_coef={ceiling_coefficient_per_m2}")
    return {
        "floors_count": floors_count,
        "foundation_price_per_m2_fallback": foundation_price_per_m2,
        "floor_coefficient_per_m2": floor_coefficient_per_m2,
        "ceiling_coefficient_per_m2": ceiling_coefficient_per_m2,
        "house_area_m2": area_used
    }

def load_wall_finishes():
    trace("load_wall_finishes()")
    cfg = load_json(wall_coefficients_file)
    interior = cfg.get("interior", {})
    exterior = cfg.get("exterior", {})
    def unit(side: dict) -> float:
        if "finish_price_per_m2" in side:
            return float(side["finish_price_per_m2"])
        layers = side.get("layers", {})
        return float(sum(float(v) for v in layers.values())) if layers else 0.0
    u = {"interior_unit": unit(interior), "exterior_unit": unit(exterior)}
    trace(f"wall finishes unit => {u}")
    return u

def load_offer_coeffs():
    trace("load_offer_coeffs()")
    try:
        cfg = load_json(offer_coefficients_file)
    except FileNotFoundError:
        cfg = {"organization_markup": 0.05, "supervising_markup": 0.03, "profit_margin": 0.10, "vat": 0.19}
        trace("offer_coefficients.json lipsește, folosesc defaults")
    out = {
        "organization_markup": float(cfg.get("organization_markup", 0.0)),
        "supervising_markup": float(cfg.get("supervising_markup", 0.0)),
        "profit_margin": float(cfg.get("profit_margin", 0.0)),
        "vat": float(cfg.get("vat", 0.0)),
    }
    trace(f"offer coeffs => {out}")
    return out

# -------- start calc ----------
plan_count_env = os.getenv("PLAN_COUNT", "1")
try:
    PLAN_COUNT = int(plan_count_env)
except ValueError:
    PLAN_COUNT = 1

trace(f"PLAN_COUNT (din ENV) = {PLAN_COUNT}")

trace("== START READ INPUTS (multi-plan) ==")
A = float(get_house_area())
interior_walls_area_gross, exterior_walls_area_gross = load_walls_areas()
openings = load_openings_all()
roof_data = load_json(roof_price_file)
trace("== END READ INPUTS ==")

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

stream_text(f"[house_pricing] PLAN_COUNT={PLAN_COUNT}, A_total={A:.2f} m², walls gross int={interior_walls_area_gross:.2f} m², ext={exterior_walls_area_gross:.2f} m²")

# ----- openings: arii scăzute + costuri
trace("calc: openings (ferestre/uși)")
subtract_area_interior = subtract_area_exterior = 0.0
cost_windows = cost_doors_int = cost_doors_ext = 0.0
openings_calc = []

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

    entry = {"type": typ, "status": status, "width_m": width, "height_m": height, "area_m2": round(area,3)}

    if "window" in typ:
        if area < AREA_THRESHOLD_WINDOW:
            unit = PRICE_PER_WALL_INT_FALLBACK if status=="interior" else PRICE_PER_WALL_EXT_FALLBACK
            cost = area * unit
            entry["calculation"] = {
                "formula": "area_m2 × unit_wall_price",
                "values": {"area_m2": area, "unit_wall_price_eur_per_m2": unit},
                "result_eur": round(cost,2),
                "treated_as": "wall"
            }
            cost_windows += cost
        else:
            cost = area * PRICE_PER_WINDOW
            entry["calculation"] = {
                "formula": "area_m2 × PRICE_PER_WINDOW",
                "values": {"area_m2": area, "PRICE_PER_WINDOW_eur_per_m2": PRICE_PER_WINDOW},
                "result_eur": round(cost,2),
                "treated_as": "window"
            }
            cost_windows += cost
            if status == "interior":
                subtract_area_interior += area
            else:
                subtract_area_exterior += area

    elif "door" in typ:
        if status == "interior":
            cost = area * PRICE_PER_DOOR_INT
            entry["calculation"] = {
                "formula": "area_m2 × PRICE_PER_DOOR_INT",
                "values": {"area_m2": area, "PRICE_PER_DOOR_INT_eur_per_m2": PRICE_PER_DOOR_INT},
                "result_eur": round(cost,2)
            }
            cost_doors_int += cost
            subtract_area_interior += area
        else:
            cost = area * PRICE_PER_DOOR_EXT
            entry["calculation"] = {
                "formula": "area_m2 × PRICE_PER_DOOR_EXT",
                "values": {"area_m2": area, "PRICE_PER_DOOR_EXT_eur_per_m2": PRICE_PER_DOOR_EXT},
                "result_eur": round(cost,2)
            }
            cost_doors_ext += cost
            subtract_area_exterior += area

    openings_calc.append(entry)

interior_walls_area_net = max(0.0, interior_walls_area_gross - subtract_area_interior)
exterior_walls_area_net = max(0.0, exterior_walls_area_gross - subtract_area_exterior)
trace(f"areas nete: interior={interior_walls_area_net:.2f}, exterior={exterior_walls_area_net:.2f}")

# ----- pereți structură
unit_int, unit_ext, sys_debug = resolve_wall_unit_prices()
walls_calc = {
    "interior": {
        "formula": "net_area_m2 × unit_int",
        "values": {"net_area_m2": interior_walls_area_net, "unit_int_eur_per_m2": unit_int},
        "result_eur": round(interior_walls_area_net * unit_int, 2)
    },
    "exterior": {
        "formula": "net_area_m2 × unit_ext",
        "values": {"net_area_m2": exterior_walls_area_net, "unit_ext_eur_per_m2": unit_ext},
        "result_eur": round(exterior_walls_area_net * unit_ext, 2)
    }
}
trace(f"walls struct cost: int={walls_calc['interior']['result_eur']}, ext={walls_calc['exterior']['result_eur']}")

# ----- podea/tavan/fundație
area_cfg = load_area_coeffs(A)
foundation_unit, foundation_debug = resolve_foundation_unit(area_cfg["foundation_price_per_m2_fallback"])
foundation_cost = round(area_cfg["house_area_m2"] * foundation_unit, 2)
floors_cost     = area_cfg["house_area_m2"] * area_cfg["floor_coefficient_per_m2"] * area_cfg["floors_count"]
floor_final     = round(foundation_cost + floors_cost, 2)
ceiling_final   = round(area_cfg["house_area_m2"] * area_cfg["ceiling_coefficient_per_m2"] * area_cfg["floors_count"], 2)
trace(f"foundation={foundation_cost}, floors={floors_cost:.2f} => floor_total={floor_final}, ceiling={ceiling_final}")

floor_calc = {
    "foundation": {
        "formula": "area_m2 × foundation_unit",
        "values": {"area_m2": area_cfg["house_area_m2"], "foundation_unit_eur_per_m2": foundation_unit},
        "result_eur": foundation_cost
    },
    "floors": {
        "formula": "area_m2 × floor_coef × floors_count",
        "values": {"area_m2": area_cfg["house_area_m2"], "floor_coef_eur_per_m2": area_cfg["floor_coefficient_per_m2"], "floors_count": area_cfg["floors_count"]},
        "result_eur": round(floors_cost,2)
    },
    "total_floor_eur": floor_final
}
ceiling_calc = {
    "formula": "area_m2 × ceiling_coef × floors_count",
    "values": {"area_m2": area_cfg["house_area_m2"], "ceiling_coef_eur_per_m2": area_cfg["ceiling_coefficient_per_m2"], "floors_count": area_cfg["floors_count"]},
    "result_eur": ceiling_final
}

# ----- beci
def load_basement():
    trace("load_basement()")
    cfg = load_json(basement_config_file)
    if not bool(cfg.get("exists", False)):
        trace("nu există beci")
        return 0.0, {"exists": False}
    area_b = float(cfg.get("area_m2", A))
    coef_b = float(cfg.get("coefficient_per_m2", 0.0))
    trace(f"beci: area={area_b}, coef={coef_b}")
    return round(area_b * coef_b, 2), {"exists": True, "area_m2": area_b, "coef": coef_b}
basement_total, basement_info = load_basement()
basement_calc = {
    "exists": basement_info.get("exists", False),
    "formula": "area_beci_m2 × coef_beci_eur_per_m2",
    "values": {"area_beci_m2": basement_info.get("area_m2", 0.0), "coef_beci_eur_per_m2": basement_info.get("coef", 0.0)},
    "result_eur": basement_total
}

# ----- finisaje pereți
wall_fin = load_wall_finishes()
finishes_calc = {
    "interior": {
        "formula": "net_area_int_m2 × finish_unit_int",
        "values": {"net_area_int_m2": interior_walls_area_net, "finish_unit_int_eur_per_m2": wall_fin["interior_unit"]},
        "result_eur": round(interior_walls_area_net * wall_fin["interior_unit"], 2)
    },
    "exterior": {
        "formula": "net_area_ext_m2 × finish_unit_ext",
        "values": {"net_area_ext_m2": exterior_walls_area_net, "finish_unit_ext_eur_per_m2": wall_fin["exterior_unit"]},
        "result_eur": round(exterior_walls_area_net * wall_fin["exterior_unit"], 2)
    }
}
trace(f"finishes: int={finishes_calc['interior']['result_eur']}, ext={finishes_calc['exterior']['result_eur']}")

# ----- servicii
def base_electricity_coef():
    cfg = load_json(electricity_coeff_file)
    return float(cfg["coefficient_electricity_per_m2"])

def sewage_total(area_m2: float):
    cfg = load_json(sewage_coeff_file)
    return round(area_m2 * float(cfg["coefficient_sewage_per_m2"]), 2)

def heating_total(area_m2: float):
    cfg = load_json(heating_coeff_file)
    base = float(cfg["coefficient_heating_per_m2"])
    t = (cfg.get("type") or "gaz").lower()
    tcoef = float((cfg.get("type_coefficients") or {}).get(t, 1.0))
    return round(area_m2 * base * tcoef, 2), {"type": t, "base_coef": base, "type_coef": tcoef}

tipS, gradP, fund, nivelOferta, hasVent, util, nivelE, acces, teren = _read_system_selection()
ENERGETIC_TABLE = {
    "STANDARD": 1.00, "KFW55": 1.05, "KFW 55": 1.05,
    "KFW40": 1.08, "KFW 40": 1.08,
    "KFW40PLUS": 1.12, "KFW 40 PLUS": 1.12, "KFW 40+": 1.12
}
ener_key = (nivelE or "STANDARD").strip().upper()
energetic_coef = ENERGETIC_TABLE.get(ener_key, 1.00)

ACCESS_TABLE = {"USOR":1.00,"UȘOR":1.00,"MEDIU":1.03,"DIFICIL":1.06}
TEREN_TABLE  = {"PLAN":1.00,"PANTA_USOARA":1.05,"PANTĂ_USOARĂ":1.05,"PANTA_MARE":1.10,"PANTĂ_MARE":1.10}
acces_coef = ACCESS_TABLE.get((acces or "USOR").strip().upper(), 1.00)
teren_coef = TEREN_TABLE.get((teren or "PLAN").strip().upper(), 1.00)

elec_unit = base_electricity_coef()
Electricity_total = round(A * elec_unit * energetic_coef, 2)
Sewage_total      = sewage_total(A)
Heating_total, heating_meta = heating_total(A)

Ventilation_total = 0.0
vent_calc = None
if hasVent and ventilation_coeffs_file.exists():
    vcfg = load_json(ventilation_coeffs_file)
    v_unit = float(vcfg.get("price_per_m2", 30.0))
    Ventilation_total = round(A * v_unit, 2)
    vent_calc = {
        "formula": "area_m2 × ventilation_unit",
        "values": {"area_m2": A, "ventilation_unit_eur_per_m2": v_unit},
        "result_eur": Ventilation_total
    }

services_calc = {
    "electricity": {
        "formula": "area_m2 × coef_electricitate × energetic_coef",
        "values": {"area_m2": A, "coef_electricitate_eur_per_m2": elec_unit, "energetic_coef": energetic_coef},
        "result_eur": Electricity_total
    },
    "sewage": {
        "formula": "area_m2 × coef_canalizare",
        "values": {"area_m2": A, "coef_canalizare_eur_per_m2": round(Sewage_total / A, 4) if A else 0.0},
        "result_eur": Sewage_total
    },
    "heating": {
        "formula": "area_m2 × coef_incalzire × type_coef",
        "values": {"area_m2": A, "coef_incalzire_eur_per_m2": heating_meta["base_coef"], "type": heating_meta["type"], "type_coef": heating_meta["type_coef"]},
        "result_eur": Heating_total
    },
    "ventilation": vent_calc or {"skipped": True}
}
trace(f"services: el={Electricity_total}, sw={Sewage_total}, ht={Heating_total}, vent={Ventilation_total}")

# ----- roof split
roof_structure_part = float(roof_base_avg) + float(roof_extra_walls)
roof_house_extras   = float(roof_sheet_metal) + float(roof_insulation)
trace(f"roof split: structure_part={roof_structure_part}, extras={roof_house_extras}")

# ----- totaluri intermediare
cost_walls_int_structure = walls_calc["interior"]["result_eur"]
cost_walls_ext_structure = walls_calc["exterior"]["result_eur"]

Final_struct = round(
    (floor_final + roof_structure_part + ceiling_final + basement_total)
    + cost_walls_int_structure + cost_walls_ext_structure,
    2
)
trace(f"Final_struct={Final_struct}")

Cost_ferestre = round(cost_windows, 2)
Cost_usi      = round(cost_doors_int + cost_doors_ext, 2)
Cost_deschideri_total = round(Cost_ferestre + Cost_usi, 2)
Services_total = round(Electricity_total + Sewage_total + Heating_total + Ventilation_total, 2)
Finisaje_total = round(finishes_calc["interior"]["result_eur"] + finishes_calc["exterior"]["result_eur"], 2)
trace(f"openings={Cost_deschideri_total}, services={Services_total}, finishes={Finisaje_total}")

if (nivelOferta or "").upper() == "STRUCTURA":
    Final_house_before_context = Final_struct
    nivel_key = "STRUCTURA"
elif (nivelOferta or "").upper() == "STRUCTURA_FERESTRE":
    Final_house_before_context = Final_struct + Cost_deschideri_total
    nivel_key = "STRUCTURA_FERESTRE"
else:
    Final_house_before_context = (
        Final_struct
        + roof_house_extras
        + Cost_deschideri_total
        + Finisaje_total
        + Services_total
    )
    nivel_key = "CASA_COMPLETA"
trace(f"nivel={nivel_key}, pre_context={Final_house_before_context}")

# ofertare
offer = load_offer_coeffs()
org_pct_base = offer["organization_markup"]
if not bool(util.get("curent", True)) or not bool(util.get("apa", True)):
    org_pct_effective = org_pct_base + 0.01
else:
    org_pct_effective = org_pct_base

organization_component = Final_house_before_context * org_pct_effective
organization_component_context = organization_component * acces_coef * teren_coef
supervising_component  = Final_house_before_context * offer["supervising_markup"]
profit_component       = Final_house_before_context * offer["profit_margin"]

Semi_value  = round(Final_house_before_context + organization_component_context + supervising_component + profit_component, 2)
Final_offer = round(Semi_value * (1.0 + offer["vat"]), 2)

stream_text(f"[house_pricing] nivel={nivel_key}, org_eff={org_pct_effective:.4f}, acces={acces_coef:.3f}, teren={teren_coef:.3f}, energetic={energetic_coef:.3f}")
trace(f"semi={Semi_value}, final_offer={Final_offer}")

# -------- OUTPUT EXTINS („calculations”) ----------
result = {
    "meta": {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "currency": "EUR",
        "plans_count": PLAN_COUNT
    },
    "summary": {
        "house_area_m2": round(area_cfg["house_area_m2"], 2),
        "final_structure_eur": Final_struct,
        "final_house_eur": Final_house_before_context,
        "offer": {
            "value_semi_eur": Semi_value,
            "final_offer_eur": Final_offer,
            "coefficients": {
                "organization_markup_base": org_pct_base,
                "organization_markup_effective": org_pct_effective,
                "supervising_markup": offer["supervising_markup"],
                "profit_margin": offer["profit_margin"],
                "vat": offer["vat"],
                "acces_coef": acces_coef,
                "teren_coef": teren_coef,
                "energetic_coef": energetic_coef
            }
        }
    },
    "roof_breakdown": {
        "roof_base_avg_eur": roof_base_avg,
        "sheet_metal_eur": roof_sheet_metal,
        "extra_walls_eur": roof_extra_walls,
        "insulation_eur": roof_insulation,
        "roof_final_total_eur": roof_total_final if roof_total_final is not None else round(roof_base_avg + roof_sheet_metal + roof_extra_walls + roof_insulation, 2)
    },
    "system_and_prefab": {
        "system": sys_debug.get("base_used", {}).get("system") if sys_debug.get("base_used") else "FALLBACK",
        "prefab": sys_debug.get("modifier_used", {}).get("prefab") if sys_debug.get("modifier_used") else "FALLBACK",
        "unit_prices_applied": {
            "interior_eur_per_m2": round(unit_int, 2),
            "exterior_eur_per_m2": round(unit_ext, 2)
        }
    },
    "foundation": {
        "tipFundatie_key": foundation_debug.get("tipFundatie_key"),
        "unit_price_eur_per_m2": round(foundation_unit, 2),
        "foundation_area_m2": round(area_cfg["house_area_m2"], 2),
        "foundation_cost_eur": foundation_cost
    },
    "components": {
        "openings": {
            "windows_total_eur": Cost_ferestre,
            "doors_total_eur": Cost_usi,
            "items": openings_calc
        },
        "walls_structure": {
            "calculations": walls_calc
        },
        "floor_system": {
            "calculations": floor_calc
        },
        "ceiling_system": {
            "calculations": ceiling_calc
        },
        "basement_system": {
            "calculations": basement_calc
        },
        "wall_finishes": {
            "calculations": finishes_calc
        },
        "services": {
            "calculations": services_calc,
            "totals": {
                "electricity_eur": Electricity_total,
                "sewage_eur": Sewage_total,
                "heating_eur": Heating_total,
                "ventilation_eur": Ventilation_total,
                "services_sum_eur": Services_total
            }
        }
    },
    "offer_calculations": {
        "level_selected": nivel_key,
        "pre_context_house_value_eur": Final_house_before_context,
        "organization_component": {
            "formula": "pre_context × org_pct_effective × acces_coef × teren_coef",
            "values": {
                "pre_context": Final_house_before_context,
                "org_pct_effective": org_pct_effective,
                "acces_coef": acces_coef,
                "teren_coef": teren_coef
            },
            "result_eur": round(organization_component_context, 2)
        },
        "supervising_component": {
            "formula": "pre_context × supervising_pct",
            "values": {"pre_context": Final_house_before_context, "supervising_pct": offer["supervising_markup"]},
            "result_eur": round(supervising_component, 2)
        },
        "profit_component": {
            "formula": "pre_context × profit_pct",
            "values": {"pre_context": Final_house_before_context, "profit_pct": offer["profit_margin"]},
            "result_eur": round(profit_component, 2)
        },
        "semi_value": {
            "formula": "pre_context + org_ctx + supervising + profit",
            "values": {
                "pre_context": Final_house_before_context,
                "org_ctx": round(organization_component_context,2),
                "supervising": round(supervising_component,2),
                "profit": round(profit_component,2)
            },
            "result_eur": Semi_value
        },
        "final_offer": {
            "formula": "semi_value × (1 + VAT)",
            "values": {"semi_value": Semi_value, "VAT": offer["vat"]},
            "result_eur": Final_offer
        }
    }
}

# 👇 atașăm și snapshot-ul per-plan (date brute)
try:
    result["engine_plans"] = collect_per_plan_data()
except Exception as e:
    trace(f"[WARN] collect_per_plan_data a eșuat: {e}")

dump_json(output_file, result)
stream_json(output_file)
print(f"✅ Rezumat complet salvat în {output_file}", flush=True)

# ======================================================
# ✅ CADRAN 8 — Generare ofertă PDF (declanșat de aici)
#     - import cu fallback al generatorului
#     - begin_stage / finalize_stage în UI dacă există
#     - upload către backend dacă API_URL/OFFER_ID/ENGINE_SECRET sunt prezente
# ======================================================

def _import_offer_pdf_module():
    """
    Returnează modulul offer_pdf (nu doar funcția), ca să putem apela și
    _upload_offer_pdf_to_backend, _fetch_fresh_export_url, _maybe_notify_livefeed_final.
    """
    trace("Import offer_pdf module (fallback: offer_pdf.py / oferta/offer_pdf.py)")
    try:
        import offer_pdf as mod
        trace("Import direct offer_pdf OK")
        return mod
    except ImportError:
        import importlib.util
        PROJECT_ROOT = PRJ
        spec_path = PROJECT_ROOT / "offer_pdf.py"
        if not spec_path.exists():
            spec_path = PROJECT_ROOT / "oferta" / "offer_pdf.py"
        spec = importlib.util.spec_from_file_location("offer_pdf", str(spec_path))
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader, "Nu pot încărca offer_pdf.py"
        spec.loader.exec_module(mod)
        trace(f"Import din {spec_path} OK")
        return mod

def _upload_pdf_if_possible(pdf_path: str):
    """
    Dacă avem API_URL, OFFER_ID și ENGINE_SECRET în env:
      1) POST /file/presign
      2) PUT upload la URL semnat
      3) POST /file pentru înregistrare în DB
    """
    api      = (os.getenv("API_URL") or "").rstrip("/")
    offer_id = os.getenv("OFFER_ID") or ""
    secret   = os.getenv("ENGINE_SECRET") or ""
    trace(f"Upload check: api={'set' if api else 'missing'}, offer_id={'set' if offer_id else 'missing'}, secret={'set' if secret else 'missing'}")
    if not (pdf_path and api and offer_id and secret):
        if not pdf_path:
            print("[INFO] PDF negenerat – sar peste upload.", flush=True)
        else:
            print("[INFO] Lipsesc API_URL/OFFER_ID/ENGINE_SECRET – sar peste upload.", flush=True)
        return

    try:
        import requests
        from pathlib import Path as _P
        pdf_file = _P(pdf_path)
        mime = "application/pdf"

        trace("3.1) presign POST /file/presign")
        r1 = requests.post(
            f"{api}/offers/{offer_id}/file/presign",
            json={"filename": pdf_file.name, "contentType": mime, "size": pdf_file.stat().st_size},
            headers={"Content-Type": "application/json", "x-engine-secret": secret},
            timeout=30
        )
        r1.raise_for_status()
        pres = r1.json()

        trace("3.2) PUT upload către URL semnat")
        r2 = requests.put(pres["uploadUrl"], data=pdf_file.read_bytes(),
                          headers={"Content-Type": mime}, timeout=120)
        r2.raise_for_status()

        trace("3.3) POST /file (register în DB)")
        r3 = requests.post(
            f"{api}/offers/{offer_id}/file",
            json={
                "storagePath": pres["storagePath"],
                "meta": {"filename": pdf_file.name, "kind": "offerPdf", "mime": mime}
            },
            headers={"Content-Type": "application/json", "x-engine-secret": secret},
            timeout=30
        )
        r3.raise_for_status()
        print("✅ PDF urcat în storage și înregistrat în backend.", flush=True)
        trace("Upload PDF complet OK")
    except Exception as e:
        print(f"[WARN] Upload PDF a eșuat: {e}", flush=True)

# ——— rulează CADRAN 8 aici ———
try:
    if begin_stage:
        trace("begin_stage: offer_pdf (din house_pricing)")
        begin_stage(
            "offer_pdf",
            title="Generare ofertă PDF",
            plan_hint="Compilez rezultatele și generez oferta PDF pe baza datelor din UI și calcule (multi-plan)."
        )

    trace("CALL offer_pdf.generate_offer_pdf()")
    offer_mod = _import_offer_pdf_module()
    pdf_path = offer_mod.generate_offer_pdf()
    print(f"📄 PDF generat: {pdf_path}", flush=True)
    trace(f"PDF generat la: {pdf_path}")

    # 1) upload (dacă vrei, poți apela aici _upload_pdf_if_possible)
    try:
        _upload_pdf_if_possible(pdf_path)
    except Exception as e:
        trace(f"_upload_pdf_if_possible a eșuat/oprit: {e}")

    # 2) (opțional) cere un export-url „fresh” și notifică LiveFeed
    try:
        fresh = offer_mod._fetch_fresh_export_url()
    except Exception as _e:
        fresh = None
        trace(f"_fetch_fresh_export_url a eșuat: {_e}")

    try:
        offer_mod._maybe_notify_livefeed_final(fresh)
        trace("LiveFeed notificat (final)")
    except Exception as _e:
        trace(f"_maybe_notify_livefeed_final a eșuat: {_e}")

    # 3) (opțional) trimite și evenimentul suplimentar „PDF upload complet”
    try:
        from net_bridge import post_event
        post_event("[house_pricing] PDF upload complet", files=[pdf_path])
        trace("LiveFeed notificat (final extra)")
    except Exception as e:
        trace(f"post_event suplimentar a eșuat/indisponibil: {e}")

finally:
    if finalize_stage:
        trace("finalize_stage: offer_pdf (din house_pricing)")
        finalize_stage("offer_pdf")

print("\n" + "="*70, flush=True)
print("🏁  EXIT house_pricing.py — totul OK (multi-plan + PDF)", flush=True)
print("="*70 + "\n", flush=True)
