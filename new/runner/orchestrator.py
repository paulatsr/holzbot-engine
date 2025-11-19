# new/runner/orchestrator.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import shutil
import os
import time
from datetime import datetime

from .config.settings import build_job_root, RUNS_ROOT
from .segmenter import segment_document, classify_segmented_plans
from .segmenter.classifier import ClassificationResult
from .floor_classifier import run_floor_classification, FloorClassificationResult
from .detections.jobs import run_detections_for_run
from .scale import run_scale_detection_for_run
from .count_objects import run_count_objects_for_run
from .exterior_doors.jobs import run_exterior_doors_for_run
from .measure_objects.jobs import run_measure_objects_for_run
from .perimeter.jobs import run_perimeter_for_run
from .area.jobs import run_area_for_run
from .roof.jobs import run_roof_for_run

# Importuri noi pentru Pricing & Offer
from .pricing.jobs import run_pricing_for_run, PricingJobResult
from .offer_builder import build_final_offer


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
        return False
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.2f}s"
        else:
            mins = int(seconds // 60)
            secs = seconds % 60
            return f"{mins}m {secs:.1f}s"


class PipelineTimer:
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
        if not self.total_start or not self.total_end:
            return
        total_time = self.total_end - self.total_start
        print("\n" + "="*70)
        print("📊 PIPELINE TIMING SUMMARY")
        print("="*70)
        for i, step in enumerate(self.steps, 1):
            duration = step["duration"]
            percentage = (duration / total_time) * 100 if total_time > 0 else 0
            bar_length = int(percentage / 2)
            bar = "█" * bar_length + "░" * (50 - bar_length)
            print(f"{i:2d}. {step['name']:30s} {Timer._format_time(duration):>10s}  {bar} {percentage:5.1f}%")
        print("-"*70)
        print(f"{'TOTAL PIPELINE TIME':30s} {Timer._format_time(total_time):>10s}")
        print("="*70 + "\n")

pipeline_timer = PipelineTimer()


# =========================================================
# DATA HANDLING
# =========================================================

def _load_frontend_data(job_root: Path) -> dict:
    """
    Încarcă datele trimise din frontend (frontend_data.json).
    Dacă nu există, încarcă fallback_frontend_data.json.
    Dacă niciunul nu există, returnează un dict gol.
    """
    # 1. Încearcă fișierul principal (generat de utilizator/frontend)
    frontend_file = Path("frontend_data.json").resolve()
    if not frontend_file.exists():
        # Încearcă în job root dacă nu e în root-ul proiectului
        frontend_file = job_root / "frontend_data.json"

    if frontend_file.exists():
        try:
            with open(frontend_file, "r", encoding="utf-8") as f:
                print(f"📥 Loading frontend data from: {frontend_file}")
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading frontend_data.json: {e}")

    # 2. Încearcă fișierul de fallback
    fallback_file = Path("fallback_frontend_data.json").resolve()
    if fallback_file.exists():
        try:
            with open(fallback_file, "r", encoding="utf-8") as f:
                print(f"📥 Loading FALLBACK data from: {fallback_file}")
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading fallback_frontend_data.json: {e}")
    
    print("⚠️ No frontend data found. Using empty dict.")
    return {}


@dataclass
class PlanInfo:
    job_root: Path
    image_path: Path

@dataclass
class ClassifiedPlanInfo:
    job_root: Path
    image_path: Path
    label: str

def _create_run_for_detections(job_root: Path, house_plans: list[ClassifiedPlanInfo]) -> str:
    run_id = job_root.name
    run_dir = RUNS_ROOT / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {"plans": [str(p.image_path) for p in house_plans]}
    (run_dir / "plans_list.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return run_id


# =========================================================
# PIPELINE
# =========================================================

def run_segmentation_for_document(input_path: str | Path, job_id: str | None = None) -> tuple[Path, list[PlanInfo]]:
    input_path = Path(input_path).resolve()
    job_root = build_job_root(job_id=job_id, prefix="segmentation_job")
    segmentation_out = job_root / "segmentation"
    segmentation_out.mkdir(parents=True, exist_ok=True)
    
    with Timer("SEGMENTATION") as t:
        plan_paths = segment_document(input_path, segmentation_out)
    pipeline_timer.add_step("Segmentation", t.end_time - t.start_time)
    
    plans = [PlanInfo(job_root=job_root, image_path=Path(p).resolve()) for p in plan_paths]
    return job_root, plans

def run_segmentation_and_classification_for_document(input_path: str | Path, job_id: str | None = None):
    pipeline_timer.start()
    input_path = Path(input_path).resolve()
    job_root = build_job_root(job_id=job_id, prefix="segmentation_job")

    # 1. SEGMENTATION
    with Timer("STEP 1: Segmentation") as t:
        segmentation_out = job_root / "segmentation"
        segmentation_out.mkdir(parents=True, exist_ok=True)
        plan_paths = segment_document(input_path, segmentation_out)
    pipeline_timer.add_step("1. Segmentation", t.end_time - t.start_time)

    if not plan_paths:
        pipeline_timer.finish()
        return job_root, [], []

    # 2. CLASSIFICATION
    with Timer("STEP 2: Classification") as t:
        cls_results = classify_segmented_plans(segmentation_out)
    pipeline_timer.add_step("2. Classification", t.end_time - t.start_time)
    
    plans = [ClassifiedPlanInfo(job_root=job_root, image_path=r.image_path, label=r.label) for r in cls_results]

    # 3. FLOOR CLASSIFICATION
    with Timer("STEP 3: Floor Classification") as t:
        floor_results = run_floor_classification(job_root, plans)
    pipeline_timer.add_step("3. Floor Classification", t.end_time - t.start_time)

    house_plans = [p for p in plans if p.label == "house_blueprint"]
    
    if house_plans:
        run_id = _create_run_for_detections(job_root, house_plans)
        
        # Încărcăm datele din Frontend AICI pentru a le avea disponibile
        frontend_data = _load_frontend_data(job_root)

        # 4. DETECTIONS
        with Timer("STEP 4: Detections") as t:
            run_detections_for_run(run_id)
        pipeline_timer.add_step("4. Detections", t.end_time - t.start_time)

        # 5. SCALE
        with Timer("STEP 5: Scale Detection") as t:
            run_scale_detection_for_run(run_id)
        pipeline_timer.add_step("5. Scale", t.end_time - t.start_time)

        # 6. COUNT OBJECTS
        with Timer("STEP 6: Count Objects") as t:
            run_count_objects_for_run(run_id)
        pipeline_timer.add_step("6. Count Objects", t.end_time - t.start_time)

        # 7. EXTERIOR DOORS
        with Timer("STEP 7: Exterior Doors") as t:
            run_exterior_doors_for_run(run_id)
        pipeline_timer.add_step("7. Exterior Doors", t.end_time - t.start_time)

        # 8. MEASURE OBJECTS
        with Timer("STEP 8: Measure Objects") as t:
            run_measure_objects_for_run(run_id)
        pipeline_timer.add_step("8. Measure Objects", t.end_time - t.start_time)

        # 9. PERIMETER
        with Timer("STEP 9: Perimeter") as t:
            run_perimeter_for_run(run_id)
        pipeline_timer.add_step("9. Perimeter", t.end_time - t.start_time)

        # 10. AREA
        with Timer("STEP 10: Area") as t:
            run_area_for_run(run_id)
        pipeline_timer.add_step("10. Area", t.end_time - t.start_time)

        # 11. ROOF
        # Transmitem datele despre acoperiș din frontend (dacă sunt necesare în modulul roof)
        # Momentan modulul roof rulează pe geometrie, dar tipul de acoperiș din frontend
        # va fi folosit la PRICING.
        with Timer("STEP 11: Roof") as t:
            run_roof_for_run(run_id)
        pipeline_timer.add_step("11. Roof", t.end_time - t.start_time)

        # 12. PRICING
        # Aici pasăm datele din frontend_data.json
        with Timer("STEP 12: Pricing") as t:
            pricing_results = run_pricing_for_run(run_id, frontend_data_override=frontend_data)
        pipeline_timer.add_step("12. Pricing", t.end_time - t.start_time)

        # 13. OFFER GENERATION
        with Timer("STEP 13: Offer Generation") as t:
            # Extragem nivelul ofertei din JSON-ul de intrare
            mat_finisaj = frontend_data.get("materialeFinisaj", {})
            offer_level = mat_finisaj.get("nivelOferta", "Structură + ferestre")
            
            total_project_cost = 0.0
            print(f"\n📋 Generare Oferte Finale (Nivel selectat: '{offer_level}'):")
            
            for res in pricing_results:
                if not res.success or not res.result_data:
                    print(f"   ❌ {res.plan_id}: Pricing failed")
                    continue
                
                final_offer = build_final_offer(
                    pricing_data=res.result_data,
                    offer_level=offer_level,
                    output_path=res.work_dir / "final_offer.json"
                )
                total_project_cost += final_offer["summary"]["total_price_eur"]
                print(f"   ✅ {res.plan_id}: {final_offer['summary']['total_price_eur']:,.2f} EUR")

            print(f"\n📊 TOTAL GENERAL PROIECT: {total_project_cost:,.2f} EUR")
        pipeline_timer.add_step("13. Offer Generation", t.end_time - t.start_time)

    pipeline_timer.finish()
    pipeline_timer.print_summary()
    return job_root, plans, floor_results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path către PDF sau imagine")
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--no-classification", action="store_true")
    args = parser.parse_args()

    if args.no_classification:
        run_segmentation_for_document(args.input, job_id=args.job_id)
    else:
        run_segmentation_and_classification_for_document(args.input, job_id=args.job_id)