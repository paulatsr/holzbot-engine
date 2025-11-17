# pip install google-generativeai pillow
import json
import os
import google.generativeai as genai
from pathlib import Path
from ui_export import record_json

# ==============================================
# CONFIGURARE
# ==============================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing in environment")
PLAN_PATH = "plan.jpg"
EXPORTS_DIR = Path("export_objects/exports")
SCALE_FILE = Path("meters_pixel/scale_result.json")
OUTPUT_FILE = Path("measure_objects/openings_measurements_gemini.json")

# ==============================================
# INITIALIZARE GEMINI
# ==============================================
genai.configure(api_key=GEMINI_API_KEY)

# ==============================================
# FUNCȚII UTILE
# ==============================================
def read_bytes(path):
    """Citește fișierul ca bytes."""
    with open(path, "rb") as f:
        return f.read()

def list_first_image(dir_path: Path):
    """Returnează prima imagine găsită în directorul dat, sau None dacă nu există."""
    if not dir_path.exists():
        print(f"⚠️  Director lipsă: {dir_path}")
        return None
    images = list(dir_path.glob("*.png")) + list(dir_path.glob("*.jpg"))
    if not images:
        print(f"⚠️  Nicio imagine găsită în: {dir_path}")
        return None
    return images[0]

def main_single_plan():
    # ==============================================
    # ÎNCĂRCARE SCALĂ
    # ==============================================
    if not SCALE_FILE.exists():
        raise FileNotFoundError(f"❌ Fișierul de scală nu există: {SCALE_FILE}")

    with open(SCALE_FILE, "r", encoding="utf-8") as f:
        scale_data = json.load(f)

    meters_per_pixel = scale_data.get("meters_per_pixel")
    if meters_per_pixel is None:
        raise ValueError("❌ Nu s-a găsit valoarea meters_per_pixel în scale_result.json")

    print(f"ℹ️  Scara folosită: {meters_per_pixel:.6f} m/pixel")

    # ==============================================
    # ÎNCĂRCARE IMAGINI TEMPLATE
    # ==============================================
    plan_bytes = read_bytes(PLAN_PATH)
    door_img = list_first_image(EXPORTS_DIR / "door")
    window_img = list_first_image(EXPORTS_DIR / "window")
    double_door_img = list_first_image(EXPORTS_DIR / "double_door")
    double_window_img = list_first_image(EXPORTS_DIR / "double_window")

    # Creăm un dicționar doar cu imaginile care există
    images_available = {
        "door": door_img,
        "window": window_img,
        "double_door": double_door_img,
        "double_window": double_window_img
    }
    images_available = {k: v for k, v in images_available.items() if v is not None}

    if not images_available:
        raise RuntimeError("❌ Nu s-a găsit nicio imagine de măsurat în export_objects/exports/")

    print(f"📦 Obiecte detectate pentru măsurare: {', '.join(images_available.keys())}")

    # ==============================================
    # PROMPT DINAMIC PENTRU GEMINI
    # ==============================================
    prompt = f"""
Imaginea principală este un plan arhitectural de locuință.
Ți se oferă {len(images_available)} imagini extrase din el ({', '.join(images_available.keys())}).

Scopul este să **estimezi lățimea reală (în metri)** a fiecărui obiect,
ținând cont că scara planului este {meters_per_pixel:.6f} metri/pixel.

🔹 Instrucțiuni clare:
- Determină lățimea fiecărei deschideri (în pixeli) și convertește-o în metri.
- Verifică proporțiile și contextul planului principal.
- Validează rezultatele față de intervalele standard:
  - Uși simple: 0.7–1.0 m
  - Geamuri simple: 0.8–1.6 m
  - Uși duble: 1.2–2.0 m
  - Geamuri duble: 1.4–3.0 m
- Dacă valoarea calculată e în afara intervalului, ajusteaz-o proporțional cu scara.
- Returnează STRICT un JSON complet, fără text explicativ suplimentar.
"""

    # ==============================================
    # STRUCTURĂ JSON DORITĂ (în prompt)
    # ==============================================
    structure = {
        "scale_meters_per_pixel": meters_per_pixel,
    }
    for key, img in images_available.items():
        structure[key] = {
            "file": img.as_posix(),
            "pixel_width_estimated": "<float>",
            "real_width_meters": "<float>",
            "validated_width_meters": "<float>",
            "validation_method": "<string>",
            "confidence": "<string>"
        }

    prompt += "\nStructură dorită:\n" + json.dumps(structure, indent=2, ensure_ascii=False)

    # ==============================================
    # SELECTARE MODEL ȘI GENERARE
    # ==============================================
    try:
        model = genai.GenerativeModel("gemini-2.5-pro")
    except Exception:
        print("⚠️  Modelul gemini-2.5-pro nu e disponibil, folosesc gemini-1.5-flash.")
        model = genai.GenerativeModel("gemini-1.5-flash")

    # Construcție conținut pentru Gemini (dinamic)
    parts = [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": plan_bytes}}]
    for key, img in images_available.items():
        parts.append({"inline_data": {"mime_type": "image/png", "data": read_bytes(img)}})

    # ==============================================
    # TRIMITERE LA GEMINI
    # ==============================================
    response = model.generate_content(
        [{"role": "user", "parts": parts}],
        generation_config={"temperature": 0}
    )

    # ==============================================
    # PARSARE RĂSPUNS
    # ==============================================
    reply = response.text.strip()
    for prefix in ("```json", "```"):
        if reply.startswith(prefix):
            reply = reply[len(prefix):].strip()
    if reply.endswith("```"):
        reply = reply[:-3].strip()

    try:
        result = json.loads(reply)
    except json.JSONDecodeError:
        print("⚠️  Răspuns invalid de la Gemini:\n", reply)
        raise

    # ==============================================
    # SALVARE FINALĂ
    # ==============================================
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    record_json(OUTPUT_FILE, stage="measure_objects",
                caption="Lățimi estimate/validate pentru uși/ferestre (m).")

    print(f"✅ Rezultatul a fost salvat în {OUTPUT_FILE}")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        # comportament original
        main_single_plan()
    else:
        cwd_backup = Path.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = Path(plan_dir)
            print(f"\n================= PLAN (measure_openings): {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
