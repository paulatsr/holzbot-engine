import json
import google.generativeai as genai
from ui_export import record_json
import os
from pathlib import Path

OUTPUT_FILE = Path("area/house_area_gemini.json")


def _plan_id() -> str | None:
    plan_id = os.getenv("PLAN_ID")
    if plan_id:
        plan_id = plan_id.strip()
    return plan_id or None


def _plan_output_path(base_path: Path) -> Path | None:
    plan_id = _plan_id()
    if not plan_id:
        return None
    return base_path.with_name(f"{base_path.stem}_{plan_id}{base_path.suffix}")


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _aggregate_house_area(base_path: Path):
    """
    Re-scrie fișierul principal cu suma tuturor house_area_gemini_pXX.json
    astfel încât scripturile ulterioare (electricitate, acoperiș etc.)
    să pornească direct de la aria totală.
    """
    plan_files = sorted(base_path.parent.glob(f"{base_path.stem}_p*.json"))
    if not plan_files:
        return

    sum_final = 0.0
    sum_scale = 0.0
    sum_labels = 0.0
    have_scale = False
    have_labels = False
    breakdown = []

    for pf in plan_files:
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
        except Exception:
            continue
        surf = data.get("surface_estimation") or {}
        final_val = float(surf.get("final_area_m2") or 0.0)
        sum_final += final_val

        if surf.get("by_scale_m2") is not None:
            have_scale = True
            sum_scale += float(surf.get("by_scale_m2") or 0.0)
        if surf.get("by_labels_m2") is not None:
            have_labels = True
            sum_labels += float(surf.get("by_labels_m2") or 0.0)

        breakdown.append({
            "plan_file": pf.name,
            "final_area_m2": round(final_val, 3),
            "method_used": surf.get("method_used"),
        })

    if sum_final <= 0:
        return

    aggregate = {
        "surface_estimation": {
            "final_area_m2": round(sum_final, 2),
            "method_used": "multi_plan_sum"
        },
        "aggregated_from_plans": True,
        "plans_count": len(breakdown),
        "plans": breakdown
    }
    if have_scale:
        aggregate["surface_estimation"]["by_scale_m2"] = round(sum_scale, 2)
    if have_labels:
        aggregate["surface_estimation"]["by_labels_m2"] = round(sum_labels, 2)

    _write_json(base_path, aggregate)

def main_single_plan():
    # 🔑 Configurare Gemini API
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing in environment")
    genai.configure(api_key=GEMINI_API_KEY)

    # 📂 Fișiere
    plan_path = "plan.jpg"
    scale_file = "meters_pixel/scale_result.json"
    output_file = str(OUTPUT_FILE)

    # 🔽 Citește valoarea metri/pixel
    with open(scale_file, "r", encoding="utf-8") as f:
        scale_data = json.load(f)

    meters_per_pixel = scale_data.get("meters_per_pixel")
    if meters_per_pixel is None:
        raise ValueError("❌ Nu s-a găsit valoarea meters_per_pixel în scale_result.json")

    print(f"ℹ️  Scara folosită: {meters_per_pixel:.6f} m/pixel")

    # 🧩 Încarcă imaginea
    with open(plan_path, "rb") as f:
        plan_bytes = f.read()

    # 🧠 Prompt îmbunătățit
    prompt = f"""
Imaginea atașată este un plan arhitectural de casă.
Scopul tău este să estimezi **suprafața totală a casei în metri pătrați**.

Fă asta în două moduri independente:

1️⃣ **Metoda bazată pe scară (geometrică)**:
   - Folosește valoarea scării {meters_per_pixel:.6f} m/pixel.
   - Estimează dimensiunile exterioare ale clădirii și calculează aria totală (inclusiv camere, fără curte).
   - Verifică dacă rezultatul e realist (o casă tipică are 70–180 m², nu sute).

2️⃣ **Metoda bazată pe etichete și legende (semantică)**:
   - Caută texte cu valori de suprafețe: m², „Gesamtfläche”, „Wohnfläche”, „Essen/Wohnen”, etc.
   - Adună toate valorile numerice care par a fi suprafețe de camere.
   - Dacă există o valoare totală (Gesamtfläche / Total), folosește-o prioritar.

3️⃣ **Analiză comparativă și selecție inteligentă**:
   - Dacă cele două metode diferă cu peste 25%, **NU face media**.
   - În schimb, alege metoda mai plauzibilă și explică motivul.
   - Dacă diferența este rezonabilă (<25%), calculează media aritmetică.

4️⃣ **Rezultat final**:
   - Returnează doar JSON, fără text suplimentar, cu această structură:

{{
  "scale_meters_per_pixel": {meters_per_pixel:.6f},
  "surface_estimation": {{
    "by_scale_m2": <float>,
    "by_labels_m2": <float>,
    "final_area_m2": <float>,
    "method_used": "<string>"
  }},
  "confidence": "<string>",
  "verification_notes": "<string>"
}}

Asigură-te că:
- Rezultatul final e realist pentru o casă unifamilială (de ex. între 50–200 m²).
- Dacă o metodă pare aberantă, marcheaz-o ca „invalid” și explică de ce.
"""

    # 🧠 Inițializează modelul
    try:
        model = genai.GenerativeModel("gemini-2.5-pro")
    except Exception:
        print("⚠️ Modelul gemini-2.5-pro nu e disponibil, folosesc gemini-1.5-flash.")
        model = genai.GenerativeModel("gemini-2.5-flash")

    # 🔥 Trimite cererea
    response = model.generate_content(
        [
            {"role": "user", "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": plan_bytes}},
            ]}
        ],
        generation_config={"temperature": 0}
    )

    # 📄 Curăță răspunsul
    reply = response.text.strip()
    for prefix in ("```json", "```"):
        if reply.startswith(prefix):
            reply = reply[len(prefix):].strip()
    if reply.endswith("```"):
        reply = reply[:-3].strip()

    # ✅ Parsează JSON
    try:
        result = json.loads(reply)
    except json.JSONDecodeError:
        print("⚠️  Răspuns invalid:\n", reply)
        raise

    # 💾 Salvează rezultatul
    _write_json(OUTPUT_FILE, result)

    plan_output = _plan_output_path(OUTPUT_FILE)
    if plan_output is not None:
        _write_json(plan_output, result)
        _aggregate_house_area(OUTPUT_FILE)

    record_json(output_file, stage="area",
                caption="Aria totală casă (două metode + alegere finală).")

    print(f"\n✅ Rezultatul a fost salvat în {output_file}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        # Comportament original: un singur plan, în cwd
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
