# new/runner/orchestrator.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import shutil
import os
import argparse

from .config.settings import build_job_root, RUNS_ROOT
from .segmenter import segment_document, classify_segmented_plans
from .segmenter.classifier import ClassificationResult
from .floor_classifier import run_floor_classification, FloorClassificationResult
from .detections.jobs import run_detections_for_run, DetectionJobResult
from .scale import run_scale_detection_for_run, ScaleJobResult
from .count_objects import run_count_objects_for_run, CountObjectsJobResult
from .exterior_doors.jobs import run_exterior_doors_for_run, ExteriorDoorsJobResult
from .measure_objects.jobs import run_measure_objects_for_run, MeasureObjectsJobResult
from .perimeter.jobs import run_perimeter_for_run, PerimeterJobResult
from .area.jobs import run_area_for_run, AreaJobResult
from .roof.jobs import run_roof_for_run, RoofJobResult

# Importuri noi pentru Pricing & Offer
from .pricing.jobs import run_pricing_for_run, PricingJobResult
from .offer_builder import build_final_offer


@dataclass
class PlanInfo:
    """
    Reprezintă un plan rezultat după segmentare.
    """
    job_root: Path
    image_path: Path


@dataclass
class ClassifiedPlanInfo:
    """
    Reprezintă un plan rezultat după segmentare + clasificare.
    """
    job_root: Path
    image_path: Path
    label: str  # house_blueprint | site_blueprint | side_view | text_area


# =========================================================
# Helper pentru legat segmenter ↔ pipeline complet
# =========================================================

def _create_run_for_detections(job_root: Path, house_plans: list[ClassifiedPlanInfo]) -> str:
    """
    Creează un RUN în carpeta runs/ astfel încât codul din etapele ulterioare
    să poată fi refolosit fără modificări.

      runs/<run_id>/plans_list.json  cu:
        {"plans": ["/abs/path/catre/plan1.png", ...]}
    """
    run_id = job_root.name  # ex: segmentation_job_20251118_155028
    run_dir = RUNS_ROOT / run_id

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Salvăm lista de planuri detectate ca house_blueprint
    payload = {
        "plans": [str(p.image_path) for p in house_plans],
    }
    (run_dir / "plans_list.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    print("\n🗂 Run pregătit pentru pipeline complet:")
    print(f"   - run_id:  {run_id}")
    print(f"   - run_dir: {run_dir}")
    print(f"   - planuri house_blueprint: {len(house_plans)}")

    return run_id


def _load_frontend_data(job_root: Path) -> dict:
    """
    Încarcă datele din frontend (dacă există) pentru a fi folosite în pricing.
    """
    frontend_file = job_root / "frontend_data.json"
    if frontend_file.exists():
        try:
            with open(frontend_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


# =========================================================
# API public pentru segmentare
# =========================================================

def run_segmentation_for_document(
    input_path: str | Path,
    job_id: str | None = None,
) -> tuple[Path, list[PlanInfo]]:
    """
    Rulează DOAR SEGMENTAREA pentru un document (PDF / imagine).
    Extrage TOATE planurile găsite în fișierul uploadat.

    Flow:
      1. Creează un job_root (ex: jobs/segmentation_job_YYYYmmdd_HHMMSS/)
      2. Creează înăuntru subfolderul 'segmentation/'
      3. Apelează segment_document(...) cu acel subfolder
      4. Împachetează rezultatele în PlanInfo

    return:
      - (job_root, [PlanInfo, PlanInfo, ...])
    """
    input_path = Path(input_path).resolve()
    job_root = build_job_root(job_id=job_id, prefix="segmentation_job")

    segmentation_out = job_root / "segmentation"
    segmentation_out.mkdir(parents=True, exist_ok=True)

    # Segmentare: extrage N planuri din input_path
    plan_paths = segment_document(input_path, segmentation_out)

    plans: list[PlanInfo] = [
        PlanInfo(job_root=job_root, image_path=Path(p).resolve())
        for p in plan_paths
    ]

    print(f"\n🧩 Job de segmentare creat:")
    print(f"   - input: {input_path}")
    print(f"   - job_root: {job_root}")
    print(f"   - segmentation_out: {segmentation_out}")
    print(f"   - planuri găsite: {len(plans)}")
    for idx, plan in enumerate(plans, start=1):
        print(f"     [{idx}] {plan.image_path.name}")

    return job_root, plans


def run_segmentation_and_classification_for_document(
    input_path: str | Path,
    job_id: str | None = None,
) -> tuple[Path, list[ClassifiedPlanInfo], list[FloorClassificationResult]]:
    """
    Rulează pipeline-ul COMPLET:
      1) Segmentare documentului în planuri multiple
      2) Clasificare planuri (house_blueprint / text_area / etc)
      3) Clasificare etaje (ground_floor / top_floor / intermediate)
      4) Detections (uși/ferestre/scări)
      5) Scale detection (meters_per_pixel)
      6) Count objects (hybrid: Roboflow + templates + Gemini)
      7) Exterior doors (flood BLUE + clasificare contact)
      8) Measure objects (lățimi uși/ferestre + arii scări)
      9) Perimeter (lungimi pereți interiori/exteriori)
      10) Area (arii pereți, podele, tavane, fundație, acoperiș)
      11) Roof (calcul preț acoperiș)
      12) Pricing (calcul global detaliat + generare ofertă)

    return:
      - job_root
      - listă de ClassifiedPlanInfo
      - listă de FloorClassificationResult
    """
    input_path = Path(input_path).resolve()
    job_root = build_job_root(job_id=job_id, prefix="segmentation_job")

    # 1) Segmentare – scoatem toate planurile din fișierul uploadat
    segmentation_out = job_root / "segmentation"
    segmentation_out.mkdir(parents=True, exist_ok=True)
    plan_paths = segment_document(input_path, segmentation_out)

    if not plan_paths:
        print("⚠️ Nu s-au găsit planuri în documentul uploadat.")
        return job_root, [], []

    # 2) Clasificare – ChatGPT Vision + fallback local
    cls_results: list[ClassificationResult] = classify_segmented_plans(segmentation_out)

    plans: list[ClassifiedPlanInfo] = [
        ClassifiedPlanInfo(
            job_root=job_root,
            image_path=r.image_path,
            label=r.label,
        )
        for r in cls_results
    ]

    print(f"\n🧩 Job de segmentare + clasificare creat:")
    print(f"   - input: {input_path}")
    print(f"   - job_root: {job_root}")
    print(f"   - segmentation_out: {segmentation_out}")
    print(f"   - planuri clasificate: {len(plans)}")
    for idx, plan in enumerate(plans, start=1):
        print(f"     [{idx}] {plan.label:15s} {plan.image_path.name}")

    # 3) Clasificare etaje (DOAR pentru house_blueprint)
    floor_results = run_floor_classification(job_root, plans)

    # 4-12) Pipeline complet doar pe house_blueprint
    house_plans = [p for p in plans if p.label == "house_blueprint"]

    if house_plans:
        run_id = _create_run_for_detections(job_root, house_plans)

        print("\n🚀 Rulez pipeline-ul complet de detecție și calcul...")
        
        # Pașii 4-11
        run_detections_for_run(run_id)
        run_scale_detection_for_run(run_id)
        run_count_objects_for_run(run_id)
        run_exterior_doors_for_run(run_id)
        run_measure_objects_for_run(run_id)
        run_perimeter_for_run(run_id)
        run_area_for_run(run_id)
        run_roof_for_run(run_id)

        # 12) Pricing & Offer Generation (NOU)
        print(f"\n💰 Rulez etapa 'pricing' & 'offer generation'...")
        
        # a) Calculăm totul brut (Pricing module returnează result_data complet)
        pricing_results: list[PricingJobResult] = run_pricing_for_run(run_id)
        
        # b) Încărcăm preferințele (nivel ofertă)
        frontend_data = _load_frontend_data(job_root)
        offer_level = frontend_data.get("nivelOferta", "Structură + ferestre")  # Fallback default
        
        total_project_cost = 0.0
        
        print(f"\n📋 Generare Oferte Finale (Nivel selectat: '{offer_level}'):")
        
        for res in pricing_results:
            if not res.success or not res.result_data:
                print(f"   ❌ {res.plan_id}: Pricing failed - {res.message}")
                continue
            
            # c) Generăm oferta finală detaliată JSON
            final_offer = build_final_offer(
                pricing_data=res.result_data,
                offer_level=offer_level,
                output_path=res.work_dir / "final_offer.json"
            )
            
            cost = final_offer["summary"]["total_price_eur"]
            total_project_cost += cost
            
            print(f"   ✅ {res.plan_id}: {cost:,.2f} EUR")
            print(f"      📄 Salvat în: {res.work_dir / 'final_offer.json'}")

        print(f"\n📊 TOTAL GENERAL PROIECT: {total_project_cost:,.2f} EUR")
        print("="*70)

    else:
        print("\nℹ️ Niciun plan house_blueprint – sar peste pipeline-ul complet.")

    return job_root, plans, floor_results


def run_single_plan_image(
    plan_image_path: str | Path,
    job_id: str | None = None,
) -> PlanInfo:
    """
    Dacă ai deja o imagine de plan (PNG/JPG) și vrei să o bagi în workflow
    ca și cum ar fi venit din segmentare.
    """
    plan_image_path = Path(plan_image_path).resolve()
    job_root = build_job_root(job_id=job_id, prefix="single_plan_job")

    plan = PlanInfo(job_root=job_root, image_path=plan_image_path)

    print(f"\n📄 Job pentru UN singur plan:")
    print(f"   - job_root: {job_root}")
    print(f"   - plan_image: {plan_image_path}")

    return plan


# =========================================================
# CLI
# =========================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Orchestrator – segmentare + clasificare + pipeline complet"
    )
    parser.add_argument("input", help="Path către PDF sau imagine")
    parser.add_argument(
        "--job-id",
        help="ID job (opțional, altfel se generează automat)",
        default=None,
    )
    parser.add_argument(
        "--no-classification",
        help="Dacă e setat, rulează DOAR segmentarea (fără clasificare + pipeline).",
        action="store_true",
    )
    args = parser.parse_args()

    if args.no_classification:
        job_root, plans = run_segmentation_for_document(
            args.input,
            job_id=args.job_id,
        )
        print("\n" + "="*70)
        print("REZUMAT FINAL (doar segmentare)")
        print("="*70)
        print(f"📂 job_root: {job_root}")
        print(f"📋 {len(plans)} planuri detectate:")
        for idx, p in enumerate(plans, start=1):
            print(f"   [{idx}] {p.image_path.name}")
        print("="*70)
    else:
        run_segmentation_and_classification_for_document(
            args.input,
            job_id=args.job_id,
        )