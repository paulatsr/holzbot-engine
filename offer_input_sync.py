#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, re, unicodedata
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
OUT_AREA = PROJECT_ROOT / "area"
OUT_ROOF = PROJECT_ROOT / "roof"
OUT_AREA.mkdir(parents=True, exist_ok=True)
OUT_ROOF.mkdir(parents=True, exist_ok=True)

# ---------- I/O helpers ----------
def _read_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _write_json(p: Path, obj: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def load_front_payload():
    """
    Caută payload-ul din frontend (mirrored de runner_http.py) în:
      ./runs/<RUN_ID>/merged_form.json
      ./ui_out/run_<RUN_ID>/merged_form.json
      ./merged_form.json
      ./export.json
    """
    run_id = os.getenv("RUN_ID", "").strip()
    candidates = []
    if run_id:
        candidates += [
            PROJECT_ROOT / "runs" / run_id / "merged_form.json",
            PROJECT_ROOT / "ui_out" / f"run_{run_id}" / "merged_form.json",
        ]
    candidates += [PROJECT_ROOT / "merged_form.json", PROJECT_ROOT / "export.json"]
    for c in candidates:
        j = _read_json(c)
        if isinstance(j, dict):
            return j
    return {}

# ---------- normalizers ----------
def _slug_uc(s: str) -> str:
    if not s:
        return ""
    x = unicodedata.normalize("NFD", s)
    x = "".join(ch for ch in x if unicodedata.category(ch) != "Mn")  # remove diacritics
    x = re.sub(r"\(.*?\)", "", x)               # drop parenthetical notes
    x = re.sub(r"[^A-Za-z0-9 ]+", " ", x)
    x = re.sub(r"\s+", " ", x).strip().upper()
    return x.replace(" ", "_")

def _norm_tip_sistem(s: str) -> str | None:
    k = _slug_uc(s).replace("_", "")
    if "CLT" in k: return "CLT"
    if "HOLZRAHMEN" in k: return "HOLZRAHMEN"
    if "MASSIVHOLZ" in k or "MASSIV" in k or "LEMNMASIV" in k: return "MASSIVHOLZ"
    return None

def _norm_grad_prefab(s: str) -> str | None:
    k = _slug_uc(s)
    if "MODULE" in k: return "MODULE"
    if "PANOUR" in k: return "PANOURI"
    if "SANTIER" in k or "MONTAJ" in k: return "SANTIER"
    return None

def _norm_fundatie(s: str) -> str | None:
    k = _slug_uc(s)
    if "PLACA" in k: return "PLACA"
    if "PILOT" in k: return "PILOTI"
    if "SOCLU" in k or "CONTINUA" in k: return "SOCLU"
    return None

def _norm_nivel_oferta(s: str) -> str:
    k = _slug_uc(s).replace("+", "_")
    if "STRUCTURA_FERESTRE" in k or "STRUCTURA__FERESTRE" in k: return "STRUCTURA_FERESTRE"
    if "STRUCTURA" in k: return "STRUCTURA"
    return "CASA_COMPLETA"

def _norm_energetic(s: str) -> str:
    k = _slug_uc(s).replace("_", "")
    if "KFW55" in k: return "KfW 55"
    if "KFW40PLUS" in k or "KFW40+" in k: return "KfW 40 PLUS"
    if "KFW40" in k: return "KfW 40"
    return "Standard"

def _norm_incalzire(s: str) -> str:
    k = _slug_uc(s)
    if "POMPA" in k: return "Pompa de căldură"
    if "ELECTRIC" in k: return "Electric"
    return "Gaz"

def _norm_acces(s: str) -> str:
    k = _slug_uc(s)
    if k.startswith("USOR"): return "USOR"
    if k.startswith("MEDIU"): return "MEDIU"
    if k.startswith("DIFICIL"): return "DIFICIL"
    # ex: "USOR_(CAMION_40T)" -> USOR
    if "USOR" in k: return "USOR"
    return "USOR"

def _norm_teren(s: str) -> str:
    k = _slug_uc(s)
    if "PANTA_MARE" in k: return "PANTA_MARE"
    if "PANTA_USOARA" in k or "PANTA_USOARA" in k: return "PANTA_USOARA"
    return "PLAN"

def norm_str(x) -> str:
    return (str(x or "")).strip()

def extract_bool(data: dict, *keys, default=False):
    for k in keys:
        if k in data:
            v = data.get(k)
            if isinstance(v, bool): return v
            if isinstance(v, (int, float)) and v in (0, 1): return bool(v)
            if isinstance(v, str):
                vv = v.strip().lower()
                if vv in ("1","true","da","yes","y","on"): return True
                if vv in ("0","false","nu","no","n","off"): return False
    return default

# ---------- main ----------
def main():
    front = load_front_payload() or {}
    data  = front.get("data") or front  # suport și payload direct

    # ---- surse plate și grupate (defensive)
    sistem = data.get("sistemConstructiv") or {}
    materiale = data.get("materialeFinisaj") or {}
    performanta = data.get("performanta") or {}
    logistica = data.get("logistica") or {}

    # ---- extragere cu fallback între forme
    tip_sistem       = norm_str(data.get("tipSistem") or sistem.get("tipSistem"))
    grad_prefab      = norm_str(data.get("gradPrefabricare") or sistem.get("gradPrefabricare"))
    tip_fundatie     = norm_str(data.get("tipFundatie") or sistem.get("tipFundatie") or (data.get("fundatie") or {}).get("tip"))
    tip_acoperis     = norm_str(data.get("tipAcoperis") or sistem.get("tipAcoperis"))

    nivel_oferta_raw = norm_str(data.get("nivelOferta") or materiale.get("nivelOferta"))
    tamplarie_raw    = data.get("tamplarie") or materiale.get("tamplarie")
    if isinstance(tamplarie_raw, dict):
        tip_tamplarie = norm_str(tamplarie_raw.get("tip"))
    else:
        tip_tamplarie = norm_str(tamplarie_raw)

    nivel_energetic  = norm_str(data.get("nivelEnergetic") or performanta.get("nivelEnergetic"))
    incalzire_raw    = norm_str(data.get("incalzire") or performanta.get("incalzire"))
    ventilatie       = extract_bool(data, "ventilatie", "ventilatieRecuperare", "ventilatie_recuperare",
                                    default=extract_bool(performanta, "ventilatie", default=False))

    acces_santier    = norm_str(data.get("accesSantier") or logistica.get("accesSantier"))
    teren            = norm_str(data.get("teren") or logistica.get("teren"))

    # utilități: bool unic în formular -> map la ambele
    utilitati_bool   = extract_bool(data, "utilitati", default=extract_bool(logistica, "utilitati", default=True))
    has_power = extract_bool(data, "utilitatiCurent", "hasPower", default=utilitati_bool)
    has_water = extract_bool(data, "utilitatiApa", "hasWater", default=utilitati_bool)

    # ---- NORMALIZARE către cheile interne
    tip_sistem_n   = _norm_tip_sistem(tip_sistem) or tip_sistem or ""
    grad_prefab_n  = _norm_grad_prefab(grad_prefab) or grad_prefab or ""
    tip_fundatie_n = _norm_fundatie(tip_fundatie) or tip_fundatie or ""
    nivel_oferta_n = _norm_nivel_oferta(nivel_oferta_raw) if nivel_oferta_raw else "CASA_COMPLETA"
    nivel_energ_n  = _norm_energetic(nivel_energetic) if nivel_energetic else "Standard"
    incalzire_n    = _norm_incalzire(incalzire_raw) if incalzire_raw else "Gaz"
    acces_n        = _norm_acces(acces_santier) if acces_santier else "USOR"
    teren_n        = _norm_teren(teren) if teren else "PLAN"

    # ---- scrieri pe disc
    if tip_acoperis:
        _write_json(OUT_ROOF / "selected_roof.json", {"tipAcoperis": tip_acoperis})

    system_selected = {
        "tipSistem": tip_sistem_n,                 # CLT | HOLZRAHMEN | MASSIVHOLZ
        "gradPrefabricare": grad_prefab_n,         # PANOURI | MODULE | SANTIER
        "tipFundatie": tip_fundatie_n,             # PLACA | PILOTI | SOCLU
        "tipAcoperis": tip_acoperis,               # păstrăm denumirea frontend (nu e folosită la coef. aici)
        "tamplarie_tip": tip_tamplarie,            # informativ; coef. finite în alt script
        "nivelOferta": nivel_oferta_n,             # STRUCTURA | STRUCTURA_FERESTRE | CASA_COMPLETA
        "nivelEnergetic": nivel_energ_n,           # Standard | KfW 55 | KfW 40 | KfW 40 PLUS
        "incalzire": incalzire_n,                  # Gaz | Pompa de căldură | Electric
        "ventilatie_recuperare": bool(ventilatie),
        "accesSantier": acces_n,                   # USOR | MEDIU | DIFICIL
        "teren": teren_n,                          # PLAN | PANTA_USOARA | PANTA_MARE
        "utilitati_site": {"curent": bool(has_power), "apa": bool(has_water)},
        "saved_at": datetime.utcnow().isoformat() + "Z"
    }
    _write_json(OUT_AREA / "system_selected.json", system_selected)

    # ---- log vizibil în pipeline
    print(f"✅ offer_input_sync")
    print(f"   sistem='{tip_sistem}' -> '{tip_sistem_n}', prefab='{grad_prefab}' -> '{grad_prefab_n}', fundatie='{tip_fundatie}' -> '{tip_fundatie_n}'")
    print(f"   nivelOferta='{nivel_oferta_raw}' -> '{nivel_oferta_n}', energetic='{nivel_energetic}' -> '{nivel_energ_n}', incalzire='{incalzire_raw}' -> '{incalzire_n}'")
    print(f"   acces='{acces_santier}' -> '{acces_n}', teren='{teren}' -> '{teren_n}', utilitati: curent={bool(has_power)}, apa={bool(has_water)}")
    if tip_acoperis:
        print(f"   tipAcoperis='{tip_acoperis}' -> scris în roof/selected_roof.json")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
