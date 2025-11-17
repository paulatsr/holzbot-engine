import json
import base64
from openai import OpenAI
import os
from pathlib import Path
from ui_export import record_json

# ==============================================
# CONFIGURARE
# ==============================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY missing in environment")
client = OpenAI(api_key=OPENAI_API_KEY)
# 📂 Calea către imagine (asigură-te că plan.jpg e în același folder)
image_path = "plan.jpg"

# 📁 Folder de salvare
output_dir = Path("meters_pixel")
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "scale_result.json"

# ==============================================
# PROMPT
# ==============================================
prompt = """
Imaginea atașată este un plan arhitectural generic, utilizat doar pentru analiză vizuală și estimare.
Scopul este să **estimezi vizual scara** imaginii (metri/pixel) pe baza oricăror informații observabile:
- etichete numerice (ex: dimensiuni în metri),
- text cu suprafețe (m²),
- scară grafică,
- sau proporții între camere.

Nu trebuie să efectuezi calcule exacte de măsurare, doar o **estimare logică bazată pe observații vizuale**.
Dacă există mai multe indicii, alege cea mai coerentă valoare și explică scurt metoda în JSON.

Returnează strict un JSON cu structura următoare:

{
  "image_width_px": <int>,
  "image_height_px": <int>,
  "reference_measurement": {
    "segment_label": "<string>",
    "pixel_length_estimated": <float>,
    "real_length_meters": <float>
  },
  "meters_per_pixel": <float>,
  "verification": {
    "room_example": {
      "label": "<string>",
      "approx_dimensions": "<string>",
      "expected_area": "<string>",
      "validation": "<string>"
    }
  }
}
"""

def main_single_plan():
    # ==============================================
    # CODIFICARE IMAGINE
    # ==============================================
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")

    # ==============================================
    # TRIMITERE CĂTRE GPT-4o
    # ==============================================
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "Ești un expert în arhitectură și interpretare vizuală a planurilor de construcții. Estimează scara imaginilor în mod descriptiv și rațional."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                    }
                ]
            }
        ]
    )

    # ==============================================
    # PARSARE ȘI SALVARE RĂSPUNS
    # ==============================================
    reply = response.choices[0].message.content.strip()

    if reply.startswith("```json"):
        reply = reply[len("```json"):].strip()
    if reply.startswith("```"):
        reply = reply[len("```"):].strip()
    if reply.endswith("```"):
        reply = reply[:-3].strip()

    try:
        parsed = json.loads(reply)
    except json.JSONDecodeError as e:
        print("⚠️  Eroare: răspunsul nu este JSON valid.")
        print("Răspuns brut primit:\n", reply)
        raise e

    # ==============================================
    # SALVARE JSON ÎN meters_pixel/
    # ==============================================
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)

    record_json(output_path, stage="meters_pixel",
                caption="Estimare scară (m/pixel) + referințe vizuale.")

    print(f"✅ Rezultatul a fost salvat în {output_path}")
    print(json.dumps(parsed, indent=2, ensure_ascii=False))

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
            print(f"\n================= PLAN (analyze_scale): {plan_path} =================")

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
