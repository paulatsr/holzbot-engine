from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import shutil
import os
import argparse
import time
from datetime import datetime

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
from .pdf_generator import generate_complete_offer_pdf


# =========================================================
# TIMER UTILITIES
# =========================================================

class Timer:
    """Context manager pentru măsurarea timpului."""
    def __init__(self, step_name: str):
        self.step_name = step_name
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        print(f"\n{'='*70}")
        print(f"⏱️  START: {self.step_name}")
        print(f"{'='*70}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        
        print(f"\n{'='*70}")
        print(f"✅ FINISH: {self.step_name}")
        print(f"⏱️  Duration: {self._format_time(elapsed)}")
        print(f"{'='*70}\n")
        
        return False  # Don't suppress exceptions
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """Formatează timpul într-un mod lizibil."""
        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.2f}s"
        else:
            mins = int(seconds // 60)
            secs = seconds % 60
            return f"{mins}m {secs:.1f}s"


class PipelineTimer:
    """Tracker global pentru timpul total al pipeline-ului."""
    def __init__(self):
        self.steps = []
        self.total_start = None
        self.total_end = None
    
    def start(self):
        self.total_start = time.time()
    
    def add_step(self, name: str, duration: float):
        self.steps.append({"name": name, "duration": duration})
    
    def finish(self):
        self.total_end = time.time()
    
    def print_summary(self):
        """Afișează un rezumat complet al timpilor."""
        if not self.total_start or not self.total_end:
            return
        
        total_time = self.total_end - self.total_start
        
        print("\n" + "="*70)
        print("📊 PIPELINE TIMING SUMMARY")
        print("="*70)
        
        for i, step in enumerate(self.steps, 1):
            duration = step["duration"]
            percentage = (duration / total_time) * 100 if total_time > 0 else 0
            
            bar_length = int(percentage / 2)  # 50 chars max
            bar = "█" * bar_length + "░" * (50 - bar_length)
            
            print(f"{i:2d}. {step['name']:30s} {Timer._format_time(duration):>10s}  {bar} {percentage:5.1f}%")
        
        print("-"*70)
        print(f"{'TOTAL PIPELINE TIME':30s} {Timer._format_time(total_time):>10s}")
        print("="*70 + "\n")


# Global timer instance
pipeline_timer = PipelineTimer()


# =========================================================
# Dataclasses
# =========================================================

@dataclass
class PlanInfo:
    """Reprezintă un plan rezultat după segmentare."""
    job_root: Path
    image_path: Path


@dataclass
class ClassifiedPlanInfo:
    """Reprezintă un plan rezultat după segmentare + clasificare."""
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
    """
    run_id = job_root.name
    run_dir = RUNS_ROOT / run_id

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = {"plans": [str(p.image_path) for p in house_plans]}
    (run_dir / "plans_list.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    print(f"\n🗂 Run pregătit pentru pipeline complet:")
    print(f"   - run_id:  {run_id}")
    print(f"   - run_dir: {run_dir}")
    print(f"   - planuri house_blueprint: {len(house_plans)}")

    return run_id


def _load_frontend_data(job_root: Path) -> dict:
    """Încarcă datele din frontend (dacă există) pentru a fi folosite în pricing."""
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
    """
    input_path = Path(input_path).resolve()
    job_root = build_job_root(job_id=job_id, prefix="segmentation_job")

    segmentation_out = job_root / "segmentation"
    segmentation_out.mkdir(parents=True, exist_ok=True)

    with Timer("SEGMENTATION - Extract plans from document") as t:
        plan_paths = segment_document(input_path, segmentation_out)
    
    pipeline_timer.add_step("Segmentation", t.end_time - t.start_time)

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
    Rulează pipeline-ul COMPLET cu cronometru detaliat pentru fiecare pas.
    """
    pipeline_timer.start()
    
    input_path = Path(input_path).resolve()
    job_root = build_job_root(job_id=job_id, prefix="segmentation_job")

    # =========================================================
    # STEP 1: SEGMENTATION
    # =========================================================
    with Timer("STEP 1: Segmentation - Extract plans from document") as t:
        segmentation_out = job_root / "segmentation"
        segmentation_out.mkdir(parents=True, exist_ok=True)
        plan_paths = segment_document(input_path, segmentation_out)
    
    pipeline_timer.add_step("1. Segmentation", t.end_time - t.start_time)

    if not plan_paths:
        print("⚠️ Nu s-au găsit planuri în documentul uploadat.")
        pipeline_timer.finish()
        pipeline_timer.print_summary()
        return job_root, [], []

    # =========================================================
    # STEP 2: CLASSIFICATION
    # =========================================================
    with Timer("STEP 2: Classification - Identify plan types (GPT-4o + local)") as t:
        cls_results: list[ClassificationResult] = classify_segmented_plans(segmentation_out)
    
    pipeline_timer.add_step("2. Classification", t.end_time - t.start_time)

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

    # =========================================================
    # STEP 3: FLOOR CLASSIFICATION
    # =========================================================
    with Timer("STEP 3: Floor Classification - Identify floor levels (GPT-4o)") as t:
        floor_results = run_floor_classification(job_root, plans)
    
    pipeline_timer.add_step("3. Floor Classification", t.end_time - t.start_time)

    # =========================================================
    # PIPELINE COMPLET (doar pe house_blueprint)
    # =========================================================
    house_plans = [p for p in plans if p.label == "house_blueprint"]

    if house_plans:
        run_id = _create_run_for_detections(job_root, house_plans)

        print("\n🚀 Rulez pipeline-ul complet de detecție și calcul...")
        
        # =========================================================
        # STEP 4: DETECTIONS
        # =========================================================
        with Timer("STEP 4: Detections - Roboflow YOLO inference") as t:
            run_detections_for_run(run_id)
        pipeline_timer.add_step("4. Detections (YOLO)", t.end_time - t.start_time)
        
        # =========================================================
        # STEP 5: SCALE DETECTION
        # =========================================================
        with Timer("STEP 5: Scale Detection - Extract meters/pixel (GPT-4o)") as t:
            run_scale_detection_for_run(run_id)
        pipeline_timer.add_step("5. Scale Detection", t.end_time - t.start_time)
        
        # =========================================================
        # STEP 6: COUNT OBJECTS
        # =========================================================
        with Timer("STEP 6: Count Objects - Hybrid detection (YOLO + Templates + Gemini)") as t:
            run_count_objects_for_run(run_id)
        pipeline_timer.add_step("6. Count Objects (Hybrid)", t.end_time - t.start_time)
        
        # =========================================================
        # STEP 7: EXTERIOR DOORS
        # =========================================================
        with Timer("STEP 7: Exterior Doors - Flood fill + classification") as t:
            run_exterior_doors_for_run(run_id)
        pipeline_timer.add_step("7. Exterior Doors", t.end_time - t.start_time)
        
        # =========================================================
        # STEP 8: MEASURE OBJECTS
        # =========================================================
        with Timer("STEP 8: Measure Objects - Calculate widths from bboxes") as t:
            run_measure_objects_for_run(run_id)
        pipeline_timer.add_step("8. Measure Objects", t.end_time - t.start_time)
        
        # =========================================================
        # STEP 9: PERIMETER
        # =========================================================
        with Timer("STEP 9: Perimeter - Measure wall lengths (GPT-4o)") as t:
            run_perimeter_for_run(run_id)
        pipeline_timer.add_step("9. Perimeter", t.end_time - t.start_time)
        
        # =========================================================
        # STEP 10: AREA
        # =========================================================
        with Timer("STEP 10: Area - Calculate all surfaces (walls, floors, roof)") as t:
            run_area_for_run(run_id)
        pipeline_timer.add_step("10. Area", t.end_time - t.start_time)
        
        # =========================================================
        # STEP 11: ROOF
        # =========================================================
        with Timer("STEP 11: Roof - Calculate roof pricing") as t:
            run_roof_for_run(run_id)
        pipeline_timer.add_step("11. Roof", t.end_time - t.start_time)
        
        # =========================================================
        # STEP 12: PRICING
        # =========================================================
        with Timer("STEP 12: Pricing - Calculate all costs (raw)") as t:
            pricing_results: list[PricingJobResult] = run_pricing_for_run(run_id)
        pipeline_timer.add_step("12. Pricing", t.end_time - t.start_time)
        
        # =========================================================
        # STEP 13: OFFER GENERATION
        # =========================================================
        with Timer("STEP 13: Offer Generation - Build final offers") as t:
            frontend_data = _load_frontend_data(job_root)
            offer_level = frontend_data.get("nivelOferta", "Structură + ferestre")
            
            total_project_cost = 0.0
            
            print(f"\n📋 Generare Oferte Finale (Nivel selectat: '{offer_level}'):")
            
            for res in pricing_results:
                if not res.success or not res.result_data:
                    print(f"   ❌ {res.plan_id}: Pricing failed - {res.message}")
                    continue
                
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
        
        pipeline_timer.add_step("13. Offer Generation", t.end_time - t.start_time)
        
        # =========================================================
        # STEP 14: PDF GENERATION
        # =========================================================
        with Timer("STEP 14: PDF Generation - Create complete offer PDF") as t:
            print(f"\n📄 Generare PDF Ofertă Completă...")
            
            try:
                pdf_path = generate_complete_offer_pdf(
                    run_id=run_id,
                    output_path=None  # Path automat: output/run_id/offer_pdf/oferta_run_id.pdf
                )
                
                print(f"\n{'='*70}")
                print(f"✅ PDF GENERAT CU SUCCES!")
                print(f"{'='*70}")
                print(f"📍 Locație: {pdf_path}")
                print(f"📏 Mărime: {pdf_path.stat().st_size / 1024:.1f} KB")
                print(f"{'='*70}\n")
                
            except Exception as e:
                print(f"\n{'='*70}")
                print(f"⚠️ EROARE la generarea PDF:")
                print(f"{'='*70}")
                print(f"{e}")
                print(f"{'='*70}\n")
                import traceback
                traceback.print_exc()
        
        pipeline_timer.add_step("14. PDF Generation", t.end_time - t.start_time)

    else:
        print("\nℹ️ Niciun plan house_blueprint – sar peste pipeline-ul complet.")

    # =========================================================
    # FINAL SUMMARY
    # =========================================================
    pipeline_timer.finish()
    pipeline_timer.print_summary()

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
        description="Orchestrator – segmentare + clasificare + pipeline complet cu timing"
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
        pipeline_timer.start()
        
        job_root, plans = run_segmentation_for_document(
            args.input,
            job_id=args.job_id,
        )
        
        pipeline_timer.finish()
        
        print("\n" + "="*70)
        print("REZUMAT FINAL (doar segmentare)")
        print("="*70)
        print(f"📂 job_root: {job_root}")
        print(f"📋 {len(plans)} planuri detectate:")
        for idx, p in enumerate(plans, start=1):
            print(f"   [{idx}] {p.image_path.name}")
        print("="*70)
        
        pipeline_timer.print_summary()
    else:
        run_segmentation_and_classification_for_document(
            args.input,
            job_id=args.job_id,
        )