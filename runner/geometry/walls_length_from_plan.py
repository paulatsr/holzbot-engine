# runner/geometry/walls_length_from_plan.py
import json
import re
import time
from pathlib import Path

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from runner.core.config import get_gemini_api_key
from runner.core.paths import (
    PLAN_IMAGE,
    SCALE_RESULT_JSON,
    WALLS_MEASUREMENTS_JSON,
    PERIMETER_DIR,
)
from runner.core.multi_plan_runner import run_for_plans
from runner.ui_export import record_json


def extract_json(text: str) -> dict:
    """
    Scoate cel mai probabil obiect JSON dintr-un răspuns care poate conține
    text, cod fence, explicații etc.
    (aceeași logică ca în scriptul tău original)
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


def main_single_plan() -> None:
    """
    Versiunea pentru **un singur plan**.
    Când MULTI_PLANS e setat, cwd se schimbă în folderul fiecărui plan,
    iar path-urile din core.paths rămân relative (perimeter/, meters_pixel/, etc.)
    """
    # fișier de debug pentru răspunsul brut
    RAW_DEBUG = PERIMETER_DIR / "walls_measurements_raw.txt"
    RAW_DEBUG.parent.mkdir(parents=True, exist_ok=True)

    # 1) API key + config Gemini
    api_key = get_gemini_api_key()
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-pro")

    # 2) scara (meters_per_pixel)
    if not SCALE_RESULT_JSON.exists():
        raise FileNotFoundError(f"Lipsește fișierul de scală: {SCALE_RESULT_JSON}")

    with open(SCALE_RESULT_JSON, "r", encoding="utf-8") as f:
        scale_data = json.load(f)

    meters_per_pixel = (
        scale_data.get("meters_per_pixel")
        or scale_data.get("m_per_px")
    )
    if meters_per_pixel is None:
        raise ValueError("Nu s-a găsit 'meters_per_pixel' în scale_result.json")

    print(f"ℹ️  Scara folosită: {meters_per_pixel:.6f} m/pixel")

    # 3) imaginea planului
    if not PLAN_IMAGE.exists():
        raise FileNotFoundError(f"Lipsește imaginea planului: {PLAN_IMAGE}")
    image_bytes = PLAN_IMAGE.read_bytes()

    # 4) prompt
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

    parts = [
        {"text": prompt},
        {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}},
    ]

    generation_config = {
        "temperature": 0,
        "response_mime_type": "application/json",
    }

    # 5) apel cu retry pe 429 / ResourceExhausted (exact ca la tine)
    def call_with_retry(max_attempts: int = 4, base_delay: float = 8.0):
        attempt = 0
        last_exc: Exception | None = None
        while attempt < max_attempts:
            try:
                return model.generate_content(
                    contents=[{"role": "user", "parts": parts}],
                    generation_config=generation_config,
                )
            except ResourceExhausted as e:
                last_exc = e
                attempt += 1
                delay = base_delay * attempt
                print(
                    f"⚠️  429 / quota — reîncerc în ~{delay:.0f}s "
                    f"(attempt {attempt}/{max_attempts})"
                )
                time.sleep(delay)
            except Exception as e:
                last_exc = e
                break
        raise last_exc or RuntimeError("Eșec necunoscut la apelul Gemini.")

    response = call_with_retry()

    reply = (getattr(response, "text", None) or "").strip()
    RAW_DEBUG.write_text(reply, encoding="utf-8")

    # 6) parse JSON (cu fallback)
    try:
        result = extract_json(reply)
    except Exception:
        cleaned = reply.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[len("```"):].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        result = json.loads(cleaned)

    # 7) salvare + UI
    WALLS_MEASUREMENTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(WALLS_MEASUREMENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    record_json(WALLS_MEASUREMENTS_JSON, stage="perimeter")

    print(f"✅ Rezultatul a fost salvat în {WALLS_MEASUREMENTS_JSON}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run_for_plans(main_single_plan)
