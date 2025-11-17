# engine/perimeter/measure_walls.py
import os
import re
import json
import time
from pathlib import Path

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from ui_export import record_json

# =========================
# Config / if not
# =========================
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "plan.jpg"
SCALE_FILE = PROJECT_ROOT / "meters_pixel" / "scale_result.json"
OUT_JSON = PROJECT_ROOT / "perimeter" / "walls_measurements_gemini.json"
RAW_DEBUG = PROJECT_ROOT / "perimeter" / "walls_measurements_raw.txt"

OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
RAW_DEBUG.parent.mkdir(parents=True, exist_ok=True)

# =========================
# API key (preferă env)
# =========================
# Setează GEMINI_API_KEY în .env sau în mediul shell-ului.
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY missing in environment")
genai.configure(api_key=API_KEY)

# =========================
# Helpers: robust JSON extract
# =========================
def extract_json(text: str) -> dict:
    """
    Scoate cel mai probabil obiect JSON dintr-un răspuns care poate conține
    text, cod fence, explicații etc.
    """
    if not text:
        raise ValueError("Răspuns gol de la model.")
    # ```json {...} ```
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S | re.I)
    if m:
        return json.loads(m.group(1))

    # caută primul '{' și închide pe acolade echilibrate
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    cand = text[start : i + 1]
                    try:
                        return json.loads(cand)
                    except Exception:
                        break  # încercăm altceva mai jos

    # fallback: ia ultimul blob cu { ... }
    candidates = re.findall(r"(\{.*\})", text, re.S)
    for cand in reversed(candidates):
        try:
            return json.loads(cand)
        except Exception:
            continue

    raise ValueError("Nu am putut extrage JSON valid din răspunsul modelului.")

def main_single_plan():
    """
    Rularea normală a scriptului pentru **un singur plan** (CWD = root-ul planului).
    Path-urile se bazează pe directorul curent, ca să funcționeze și cu MULTI_PLANS.
    """
    project_root = Path(".").resolve()
    scale_file = project_root / "meters_pixel" / "scale_result.json"
    plan_path = project_root / "plan.jpg"
    out_json = project_root / "perimeter" / "walls_measurements_gemini.json"
    raw_debug = project_root / "perimeter" / "walls_measurements_raw.txt"

    out_json.parent.mkdir(parents=True, exist_ok=True)
    raw_debug.parent.mkdir(parents=True, exist_ok=True)

    # =========================
    # 1) Citește scara
    # =========================
    if not scale_file.exists():
        raise FileNotFoundError(f"Lipsește fișierul de scală: {scale_file}")

    with open(scale_file, "r", encoding="utf-8") as f:
        scale_data = json.load(f)

    meters_per_pixel = scale_data.get("meters_per_pixel") or scale_data.get("m_per_px")
    if meters_per_pixel is None:
        raise ValueError("Nu s-a găsit 'meters_per_pixel' în scale_result.json")

    print(f"ℹ️  Scara folosită: {meters_per_pixel:.6f} m/pixel")

    # =========================
    # 2) Citește imaginea
    # =========================
    if not plan_path.exists():
        raise FileNotFoundError(f"Lipsește imaginea planului: {plan_path}")
    image_bytes = plan_path.read_bytes()

    # =========================
    # 3) Prompt
    # =========================
    prompt = f"""
Imaginea atașată este un plan arhitectural.

Scopul tău este să estimezi lungimea totală a pereților INTERIORI și EXTERIORI
folosind două metode independente:

1) Estimare bazată pe pixeli — identifică pereții, estimează lungimea totală în pixeli,
   apoi convertește în metri folosind scara {meters_per_pixel:.6f} m/pixel.
2) Estimare bazată pe proporții — folosește dimensiunile explicite, ariile camerelor și forma generală
   pentru a deduce lungimile pereților.
3) Calculează media aritmetică între cele două metode pentru fiecare categorie (interior/exterior).
4) Include o evaluare a încrederii și note de verificare.

Returnează STRICT un JSON cu această structură:

{{
  "scale_meters_per_pixel": {meters_per_pixel:.6f},
  "estimations": {{
    "by_pixels": {{
      "interior_meters": <float>,
      "exterior_meters": <float>
    }},
    "by_proportion": {{
      "interior_meters": <float>,
      "exterior_meters": <float>
    }},
    "average_result": {{
      "interior_meters": <float>,
      "exterior_meters": <float>
    }}
  }},
  "confidence": "<string>",
  "verification_notes": "<string>"
}}
"""

    # =========================
    # 4) Apel model cu retry și MIME JSON
    # =========================
    model = genai.GenerativeModel("gemini-2.5-pro")

    generation_config = {
        "temperature": 0,
        # Încearcă să forțezi JSON pur; dacă serverul tot pune text, extractorul rezolvă.
        "response_mime_type": "application/json",
    }

    parts = [
        {"text": prompt},
        {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}},
    ]

    def call_with_retry(max_attempts=4, base_delay=8.0):
        attempt = 0
        last_exc = None
        while attempt < max_attempts:
            try:
                return model.generate_content(
                    contents=[{"role": "user", "parts": parts}],
                    generation_config=generation_config,
                )
            except ResourceExhausted as e:
                last_exc = e
                attempt += 1
                # backoff simplu; Gemini dă de obicei un retry_delay în mesaj
                delay = base_delay * attempt
                print(f"⚠️  429 / quota — reîncerc în ~{delay:.0f}s (attempt {attempt}/{max_attempts})")
                time.sleep(delay)
            except Exception as e:
                last_exc = e
                break
        raise last_exc

    response = call_with_retry()

    # =========================
    # 5) Parse răspuns (cu log raw)
    # =========================
    reply = (getattr(response, "text", None) or "").strip()
    raw_debug.write_text(reply, encoding="utf-8")

    try:
        result = extract_json(reply)
    except Exception:
        # curățare fence minimă, apoi încearcă încă o dată
        cleaned = reply.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[len("```"):].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        result = json.loads(cleaned)

    # =========================
    # 6) Persist + UI
    # =========================
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    record_json(out_json, stage="perimeter")

    print(f"✅ Rezultatul a fost salvat în {out_json}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        # comportament original: un singur plan
        main_single_plan()
    else:
        cwd_backup = Path.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = Path(plan_dir)
            print(f"\n================= PLAN (measure_walls): {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
