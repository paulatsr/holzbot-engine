# runner/geometry/scale_from_plan.py
import json
import base64
from pathlib import Path

from openai import OpenAI

from runner.config.settings import get_openai_api_key
from runner.utils.io import PLAN_IMAGE, METERS_PIXEL_DIR, SCALE_RESULT_JSON
from runner.workers.plan_worker import run_for_plans
from runner.ui_export import record_json  # la fel ca înainte, doar că mutat în runner/

PROMPT = """
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


def main_single_plan() -> None:
    """
    Versionea "un singur plan" – rulează în cwd-ul curent (care e fie root proiect,
    fie un subfolder de plan când MULTI_PLANS e setat).
    """
    api_key = get_openai_api_key()
    client = OpenAI(api_key=api_key)

    if not PLAN_IMAGE.exists():
        raise FileNotFoundError(f"❌ Nu găsesc {PLAN_IMAGE} în {Path.cwd()}")

    # codifică imaginea în base64 pentru GPT-4o
    with open(PLAN_IMAGE, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Ești un expert în arhitectură și interpretare vizuală a planurilor de construcții. "
                    "Estimează scara imaginilor în mod descriptiv și rațional."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            },
        ],
    )

    reply = response.choices[0].message.content.strip()

    # curățare de ```json
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

    # salvăm în meters_pixel/scale_result.json
    METERS_PIXEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCALE_RESULT_JSON, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)

    record_json(SCALE_RESULT_JSON, stage="meters_pixel",
                caption="Estimare scară (m/pixel) + referințe vizuale.")

    print(f"✅ Rezultatul a fost salvat în {SCALE_RESULT_JSON}")
    print(json.dumps(parsed, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    # gestionează MULTI_PLANS pentru noi
    run_for_plans(main_single_plan)
