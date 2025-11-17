# runner/roof/patch_roof_types_extra_walls.py
import json
from pathlib import Path
import os

from runner.ui_export import record_json

path = Path("roof/roof_types_germany.json")

EXTRA_WALLS_EUR_PER_M = {
    "Flachdach": 70,
    "Fußwalmdach": 30,
    "Kreuzdach": 110,
    "Grabendach": 90,
    "Krüppelwalmdach": 50,
    "Mansardendach": 120,
    "Mansardendach mit Fußwalm": 110,
    "Mansardendach mit Schopf": 130,
    "Mansardenwalmdach": 100,
    "Nurdach": 140,
    "Paralleldach": 70,
    "Pultdach": 80,
    "Pultdach erweitert/versetzt": 90,
    "Satteldach": 60,
    "Satteldach erweitert": 70,
    "Sattel-Walmdach": 40,
    "Scheddach / Sägezahndach": 120,
    "Schleppdach": 20,
    "Schmetterlingsdach": 100,
    "Tonnendach": 80,
    "Walmdach": 10,
    "Walm-Kehldach": 60,
    "Zeltdach": 15,
    "Zwerchdach": 60,
}


def main_single_plan():
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated, missing = 0, []
    for r in data.get("dachformen", []):
        name = r.get("name_de")
        if name in EXTRA_WALLS_EUR_PER_M:
            r["extra_walls_price_eur_per_m"] = float(EXTRA_WALLS_EUR_PER_M[name])
            updated += 1
        else:
            missing.append(name)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    record_json(
        path,
        stage="roof",
        caption="Tipuri acoperiș (DE) – coeficient extra pereți completat.",
    )

    print(f"✅ Actualizat {updated} tipuri de acoperiș.")
    if missing:
        print("⚠️ Fără coeficient pentru:", ", ".join(missing))


if __name__ == "__main__":
    plans_env = os.getenv("MULTI_PLANS")

    if not plans_env:
        main_single_plan()
    else:
        from pathlib import Path as _P

        cwd_backup = _P.cwd()
        plans = [p.strip() for p in plans_env.split(",") if p.strip()]

        for plan_dir in plans:
            plan_path = _P(plan_dir)
            print(
                f"\n================= PLAN (patch_roof_types_extra_walls): {plan_path} ================="
            )

            if not plan_path.exists():
                print(f"⚠️  Sar peste: folderul planului nu există ({plan_path})")
                continue

            try:
                os.chdir(plan_path)
                main_single_plan()
            finally:
                os.chdir(cwd_backup)
