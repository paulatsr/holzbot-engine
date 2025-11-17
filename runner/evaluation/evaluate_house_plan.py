# runner/evaluation/evaluate_house_plan.py

"""
Orchestrator principal pentru evaluarea completă a unei case
pornind de la plan (imagine/PDF) până la ofertă finală.

Rulează, pentru FIECARE plan cunoscut de multi_plan_runner:

1) Geometrie & scale
2) Detecții YOLO + template export
3) Identificare goluri (ferestre/uși)
4) Segmentează camerele și clasifică ușile exterioare
5) Măsurători goluri + agregare date + pricing goluri
6) Aria și suprafețele de pereți
7) Tipuri de acoperiș + preț acoperiș
8) Servicii (electricitate, canalizare, încălzire)
9) Rezumat final de preț casă (house_price_summary)
"""

from runner.core.multi_plan_runner import run_for_plans

# --- GEOMETRY ---
from runner.geometry.scale_from_plan import (
    main_single_plan as step_scale_from_plan,
)
from runner.geometry.walls_length_from_plan import (
    main_single_plan as step_walls_length,
)
from runner.geometry.house_area_from_plan import (
    main_single_plan as step_house_area,
)

# --- DETECTION ---
from runner.detection.import_yolo_detections import (
    main_single_plan as step_import_yolo_detections,
)
from runner.detection.export_templates_from_detections import (
    main_single_plan as step_export_templates,
)
from runner.detection.detect_openings_hybrid import (
    main_single_plan as step_detect_openings,
)

# --- SEGMENTATION ---
from runner.segmentation.rooms_from_walls import (
    main_single_plan as step_rooms_from_walls,
)
from runner.segmentation.classify_exterior_doors import (
    main_single_plan as step_classify_exterior_doors,
)

# --- OPENINGS ---
from runner.openings.measure_openings_gemini import (
    main_single_plan as step_measure_openings,
)
from runner.openings.collect_openings_data import (
    main_single_plan as step_collect_openings_data,
)
from runner.openings.openings_pricing import (
    main_single_plan as step_openings_pricing,
)

# --- AREAS ---
from runner.areas.walls_area_from_lengths import (
    main_single_plan as step_walls_area_from_lengths,
)
from runner.areas.walls_area_with_openings import (
    main_single_plan as step_walls_area_with_openings,
)

# --- ROOF ---
from runner.roof.patch_roof_types_extra_walls import (
    main_single_plan as step_patch_roof_types,
)
from runner.roof.roof_price_from_area import (
    main_single_plan as step_roof_price_from_area,
)

# --- SERVICES ---
from runner.services.electricity_from_area import (
    main_single_plan as step_electricity_from_area,
)
from runner.services.sewage_from_area import (
    main_single_plan as step_sewage_from_area,
)
from runner.services.heating_from_area import (
    main_single_plan as step_heating_from_area,
)

# --- PRICING ---
from runner.pricing.house_price_summary import (
    main_single_plan as step_house_price_summary,
)


# Ordinea pipeline-ului pentru UN SINGUR plan
PIPELINE_STEPS = [
    # 1) Geometrie & scale
    ("geometry.scale_from_plan", step_scale_from_plan),
    ("detection.import_yolo_detections", step_import_yolo_detections),
    ("detection.export_templates_from_detections", step_export_templates),
    ("detection.detect_openings_hybrid", step_detect_openings),

    # 2) Pereți & camere
    ("geometry.walls_length_from_plan", step_walls_length),
    ("segmentation.rooms_from_walls", step_rooms_from_walls),
    ("segmentation.classify_exterior_doors", step_classify_exterior_doors),

    # 3) Măsurători goluri
    ("openings.measure_openings_gemini", step_measure_openings),
    ("openings.collect_openings_data", step_collect_openings_data),
    ("openings.openings_pricing", step_openings_pricing),

    # 4) Arii pereți & casă
    ("geometry.house_area_from_plan", step_house_area),
    ("areas.walls_area_from_lengths", step_walls_area_from_lengths),
    ("areas.walls_area_with_openings", step_walls_area_with_openings),

    # 5) Acoperiș
    ("roof.patch_roof_types_extra_walls", step_patch_roof_types),
    ("roof.roof_price_from_area", step_roof_price_from_area),

    # 6) Servicii
    ("services.electricity_from_area", step_electricity_from_area),
    ("services.sewage_from_area", step_sewage_from_area),
    ("services.heating_from_area", step_heating_from_area),

    # 7) Pricing final casă
    ("pricing.house_price_summary", step_house_price_summary),
]


def _run_pipeline_for_single_plan():
    """
    Această funcție este apelată de run_for_plans pentru FIECARE plan în parte.
    Contextul (plan-ul curent, path-uri, etc.) e setat de multi_plan_runner.
    """
    print("\n================ EVALUATE HOUSE PLAN ================")

    for step_name, step_func in PIPELINE_STEPS:
        print(f"\n--- ▶ STEP: {step_name} ---")
        try:
            step_func()
            print(f"✅ DONE: {step_name}")
        except Exception as exc:
            # Poți înlocui cu logging adevărat, dacă vrei
            print(f"❌ EROARE la pasul {step_name}: {exc}")
            # poți alege: ori rupi pipeline-ul, ori continui cu următoarele
            # aici rupem ca să nu propagăm erori:
            raise

    print("\n================ PIPELINE COMPLETĂ ✅ ================")


def main():
    """
    Rulează pipeline-ul complet pentru TOATE planurile cunoscute de multi_plan_runner.
    """
    run_for_plans(_run_pipeline_for_single_plan)


if __name__ == "__main__":
    main()
