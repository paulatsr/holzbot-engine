# engine/evaluate_plan/evaluate_house_plan.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests, base64, json, time
from ui_export import record_json, record_image

import os
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing in environment")
PLAN_PATH = "plan.jpg"

with open(PLAN_PATH, "rb") as f:
    image_data = base64.b64encode(f.read()).decode("utf-8")

PROMPT = """
Ești un expert în arhitectură... (trunchiat pentru brevități — păstrează promptul tău complet)
Returnează STRICT JSON-ul cerut.
"""

url = ("https://generativelanguage.googleapis.com/v1beta/"
       "models/gemini-2.5-flash:generateContent?key=" + API_KEY)

def main_single_plan():
    payload = {
        "contents": [
            {"role": "user",
             "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_data}},
             ]}
        ],
        "generationConfig": {"temperature": 0}
    }

    for _ in range(3):
        r = requests.post(url, json=payload)
        if r.status_code != 429: break
        print("⚠️  Rate limit, retry în 10s..."); time.sleep(10)

    if r.status_code != 200:
        print("❌ Eroare API:", r.status_code, r.text); raise SystemExit(1)

    data = r.json()
    try:
        reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        print("❌ Răspuns invalid:\n", json.dumps(data, indent=2)); raise SystemExit(1)

    if reply.startswith("```json"): reply = reply[len("```json"):].strip()
    if reply.startswith("```"): reply = reply[len("```"):].strip()
    if reply.endswith("```"): reply = reply[:-3].strip()

    try:
        result = json.loads(reply)
    except json.JSONDecodeError:
        print("⚠️  Răspunsul nu e JSON valid:\n", reply); raise SystemExit(1)

    out = Path("plan_evaluation_gemini25.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    record_json(str(out), stage="evaluate_plan",
                caption="Evaluare calitate plan (Gemini 2.5): elemente măsurabile și verdict.")

    # 👉 publicăm o singură dată imaginea planului ca _01.png
    record_image(PLAN_PATH, stage="evaluate_plan")

    print("✅ Rezultatul a fost salvat în", out.name)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        # Comportament original
        main_single_plan()
    else:
        from pathlib import Path
        cwd_backup = Path.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = Path(plan_dir)
            print(f"\n================= PLAN (evaluate_house_plan): {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
