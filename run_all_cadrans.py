# engine/run_all_cadrans.py (REFACUT: fără segmentare în acest fișier)
# ===================================================================
# Acum acest runner:
#   - citește lista de planuri din runs/<RUN_ID>/plans_list.json (scrisă de detect_plans.py)
#   - rulează cadranele 1–7 pentru toate planurile
#   - CADRAN 8 (PDF) rămâne declanșat în house_pricing.py
#
# Dacă plans_list.json lipsește => eroare explicită (nu mai facem auto-segmentare aici).

import os
import sys
import time
import subprocess
import shutil
import json
from pathlib import Path
from datetime import datetime

def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def tns() -> float:
    return time.perf_counter()

def trace(msg: str):
    print(f"[{ts()}] [TRACE] {msg}", flush=True)

# .env (opțional)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name(".env"))
    trace("dotenv încărcat (dacă a existat).")
except Exception:
    trace("dotenv NU a fost încărcat (ignor).")

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PY = PROJECT_ROOT / ".venv" / "bin" / "python3"

BASE_ENV = os.environ.copy()
BASE_ENV["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + BASE_ENV.get("PYTHONPATH", "")
BASE_ENV["PYTHONUNBUFFERED"] = "1"

run_id = os.getenv("RUN_ID") or f"local_{int(time.time())}"
BASE_ENV["RUN_ID"] = run_id
BASE_ENV["UI_RUN_DIR"] = run_id
BASE_ENV["RUN_STARTED_TS"] = str(time.time())

RUNS_ROOT_ENV = os.getenv("RUNS_ROOT") or os.getenv("WORKDIR") or ""
RUNS_ROOT = Path(RUNS_ROOT_ENV) if RUNS_ROOT_ENV else (PROJECT_ROOT / "runs")
RUNS_ROOT.mkdir(parents=True, exist_ok=True)

RUN_DIR = RUNS_ROOT / run_id
RUN_DIR.mkdir(parents=True, exist_ok=True)

from ui_export import begin_stage, finalize_stage, get_run_dir
from ui_export import record_image, record_text

trace(f"UI output dir = {get_run_dir()} (RUN_ID={run_id})")
print(f"\n📁 UI output în: {get_run_dir()} (RUN_ID={run_id})", flush=True)

def run_step(title: str, rel_script: str):
    python_bin = str(VENV_PY) if VENV_PY.exists() else "python3"
    cmd = [python_bin, "-u", rel_script]
    t0 = tns()
    trace(f"START step: {title} | file={rel_script} | cmd={' '.join(cmd)} | cwd={PROJECT_ROOT}")
    print(f"\n🚀 {title}", flush=True)

    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=BASE_ENV,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    ret = proc.wait()
    dt = tns() - t0
    trace(f"END   step: {title} | exit={ret} | duration={dt:.2f}s")
    if ret != 0:
        raise RuntimeError(f"❌ Step failed: {title} (exit {ret})")

# === NOU: încărcăm lista de planuri generată de detect_plans.py
def load_plans_list():
    p = RUN_DIR / "plans_list.json"
    if not p.exists():
        raise RuntimeError("❌ lipsă runs/<RUN_ID>/plans_list.json — rulează întâi detect_plans.py")
    data = json.loads(p.read_text(encoding="utf-8"))
    plans = data.get("plans") or []
    if not plans:
        raise RuntimeError("❌ plans_list.json nu conține planuri")
    return [str(Path(x)) for x in plans]

PLANS = load_plans_list()
plan_count = len(PLANS)
BASE_ENV["PLAN_COUNT"] = str(plan_count)

# propagă tip acoperiș din export (dacă a fost mirrorizat anterior)
trace("PRE: SYNC UI INPUTS")
run_step("SYNC UI INPUTS", "offer_input_sync.py")

try:
    import json as _json
    sel_path = PROJECT_ROOT / "roof" / "selected_roof.json"
    if sel_path.exists():
        sel = _json.loads(sel_path.read_text(encoding="utf-8"))
        roof_key = (sel.get("tipAcoperis") or "").strip()
        if roof_key:
            BASE_ENV["ROOF_SELECTED"] = roof_key
            print(f"🌤 ROOF_SELECTED='{roof_key}' (propagat via ENV)", flush=True)
            trace(f"ENV set ROOF_SELECTED={roof_key}")
except Exception as e:
    print(f"[WARN] nu pot propaga ROOF_SELECTED: {e}")

def set_current_plan_env(plan_index: int, total_plans: int, plan_path: str):
    plan_id = f"p{plan_index:02d}"

    BASE_ENV["PLAN_INDEX"] = str(plan_index)
    BASE_ENV["PLAN_ID"] = plan_id
    BASE_ENV["PLAN_IMAGE"] = str(plan_path)
    BASE_ENV["PLAN_COUNT"] = str(total_plans)

    dst = PROJECT_ROOT / "plan.jpg"
    try:
        shutil.copy(plan_path, dst)
        trace(f"[PLAN {plan_index}/{total_plans}] plan curent setat: {plan_path} -> {dst}")
    except Exception as e:
        trace(f"❌ Nu pot copia planul curent în plan.jpg: {e}")
        raise

    print("\n" + "=" * 60, flush=True)
    print(f"🏠 PLAN {plan_index}/{total_plans} ({plan_id}) — {plan_path}", flush=True)
    print("=" * 60 + "\n", flush=True)

def run_for_all_plans(stage_key: str, stage_title: str, plan_hint: str, scripts):
    trace(f"begin_stage: {stage_key}")
    begin_stage(stage_key, title=stage_title, plan_hint=plan_hint)

    total = len(PLANS)
    for idx, plan_path in enumerate(PLANS, start=1):
        set_current_plan_env(idx, total, plan_path)
        try:
            record_text(f"== START {stage_key} [{idx}/{total}] ==", stage=stage_key, filename="_live.txt", append=True)
            record_image(plan_path, stage=stage_key)
        except Exception as _e:
            trace(f"[WARN] Nu pot emite marker/poză pentru plan {idx}: {_e}")

        for nice_title, rel_script in scripts:
            title = f"{nice_title} (PLAN {idx}/{total})"
            run_step(title, rel_script)

    trace(f"finalize_stage: {stage_key}")
    finalize_stage(stage_key)

print(f"\n📌 Număr de planuri detectate (din lista pregătită): {plan_count}", flush=True)
for i, p in enumerate(PLANS, start=1):
    print(f"   - Plan {i}: {p}", flush=True)

# ========== CADRAN 1 ========================================================
print("\n==========================", flush=True)
print("🧭 CADRAN 1 — Evaluare plan (fără verificare Gemini)", flush=True)
print("==========================", flush=True)

run_for_all_plans(
    stage_key="export_objects",
    stage_title="Extracție exemple obiecte",
    plan_hint="Rulez detectarea de uși/ferestre și export exemple reprezentative pentru măsurători, pentru fiecare plan.",
    scripts=[
        ("ADAUGARE EXEMPLE ROBOFLOW", "export_objects/import_detections.py"),
        ("RULARE DETECTIE USI/GEAMURI", "export_objects/run_crops.py"),
    ],
)

run_for_all_plans(
    stage_key="count_objects",
    stage_title="Numărare uși/ferestre",
    plan_hint="Combin detectarea clasică cu verificări pe fragmente greu orientate pentru a număra corect obiectele din fiecare plan.",
    scripts=[
        ("RULARE NUMĂRARE USI/GEAMURI", "count_objects/detect_all_hybrid.py"),
    ],
)

run_for_all_plans(
    stage_key="meters_pixel",
    stage_title="Estimare scară (m/pixel)",
    plan_hint="Stabilesc scara imaginii (metri/pixel) pe baza etichetelor vizibile sau a proporțiilor, separat pentru fiecare plan.",
    scripts=[
        ("CALCULARE METERS/PIXEL", "meters_pixel/analyze_scale.py"),
    ],
)

# ========== CADRAN 2 ========================================================
print("==========================", flush=True)
print("🏠 CADRAN 2 — Exterior doors", flush=True)
print("==========================", flush=True)

run_for_all_plans(
    stage_key="measure_openings",
    stage_title="Măsurare deschideri",
    plan_hint="Măsor lățimile ușilor/ferestrelor în metri pornind de la crop-uri și scara stabilită, pentru fiecare plan.",
    scripts=[
        ("MEASURE DOORS AND WINDOWS IN METERS", "measure_objects/measure_openings.py"),
    ],
)

run_for_all_plans(
    stage_key="exterior_doors",
    stage_title="Identificare uși exterioare",
    plan_hint="Segmentăm camerele și marcăm exteriorul pentru a decide care uși duc în exterior, separat pentru fiecare plan.",
    scripts=[
        ("EXTRACT NUMBER OF EXTERIOR DOORS (ROOM EXTRACTION)", "exterior_doors/room_extraction.py"),
        ("DETECT EXTERIOR DOORS", "exterior_doors/detect_exterior_doors.py"),
    ],
)

# ========== CADRAN 3 ========================================================
print("==========================", flush=True)
print("📏 CADRAN 3 — Măsurare pereți", flush=True)
print("==========================", flush=True)

run_for_all_plans(
    stage_key="perimeter",
    stage_title="Măsurare pereți",
    plan_hint="Estimez lungimile pereților interiori și exteriori + pregătesc datele de deschideri, pentru fiecare plan, urmând să cumulez rezultatele.",
    scripts=[
        ("MASURARE LUNGIME DESCHIDERI", "perimeter/openings_data.py"),
        ("MASURARE PERETI INTERIORI SI EXTERIORI", "perimeter/measure_walls.py"),
    ],
)

# ========== CADRAN 4 ========================================================
print("==========================", flush=True)
print("📐 CADRAN 4 — Calculare arie pereți", flush=True)
print("==========================", flush=True)

run_for_all_plans(
    stage_key="area_walls",
    stage_title="Calcul arie pereți",
    plan_hint="Calculez ariile pereților, scăzând deschiderile (uși/ferestre) după clasificarea lor, pentru fiecare plan; ariile vor fi apoi cumulate.",
    scripts=[
        ("CALCULARE ARIE FINALĂ PERETI", "area/calculate_wall_areas.py"),
    ],
)

# ========== CADRAN 5 ========================================================
print("==========================", flush=True)
print("🏡 CADRAN 5 — Calculare arie casă", flush=True)
print("==========================", flush=True)

run_for_all_plans(
    stage_key="area_house",
    stage_title="Calcul arie totală casă",
    plan_hint="Calculez aria fiecărui plan (etaj) și apoi le cumulez într-o singură arie totală a casei.",
    scripts=[
        ("CALCULARE ARIA CASEI", "area/calculate_total_area_gemini.py"),
    ],
)

# ========== CADRAN 6 ========================================================
print("==========================", flush=True)
print("🏗️ CADRAN 6 — Calculare preț acoperiș", flush=True)
print("==========================", flush=True)

run_for_all_plans(
    stage_key="roof",
    stage_title="Calcul preț acoperiș",
    plan_hint="Aplic costurile pe m², perimetru (tinichigerie), pereți suplimentari și izolație, per plan. La final se cumulează.",
    scripts=[
        ("CALCULARE PRET ACOPERIS", "roof/calculate_roof_price.py"),
    ],
)

# ========== CADRAN 7 ========================================================
trace("begin_stage: house_pricing")
begin_stage(
    "house_pricing",
    title="Calcul preț casă",
    plan_hint="Agreg costuri pe toate planurile (etajele) pentru o singură ofertă finală. (Declanșează intern și CADRAN 8 – PDF)."
)
run_step("CALCULARE PRET CASA", "house_pricing.py")
trace("finalize_stage: house_pricing")
finalize_stage("house_pricing")

print("✅ Toate cele 7 cadrane au fost rulate cu succes (folosind plans_list.json)!", flush=True)
trace("END pipeline run_all_cadrans.py")
