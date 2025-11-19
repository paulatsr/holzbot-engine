# new/runner/area/jobs.py
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from ..config.settings import (
    load_plan_infos,
    PlansListError,
    PlanInfo,
)

from .calculator import calculate_areas_for_plan
from .aggregator import aggregate_multi_plan_areas


STAGE_NAME = "area"


@dataclass
class AreaJobResult:
    plan_id: str
    work_dir: Path
    success: bool
    message: str
    result_data: dict | None = None


def _run_for_single_plan(
    run_id: str, 
    index: int, 
    total: int, 
    plan: PlanInfo,
    is_single_plan: bool
) -> AreaJobResult:
    """
    Calculează ariile pentru un singur plan.
    """
    work_dir = plan.stage_work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    
    # ==========================================
    # INPUT FILES - FIX PATH
    # ==========================================
    
    # Metadata file - extragem numele ORIGINAL din plan.plan_image
    # Ex: plan.plan_image = "/path/to/cluster_2.jpg" → original_name = "cluster_2"
    original_name = plan.plan_image.stem
    
    # Navighează la job_root (jobs/run_id/)
    # work_dir = output/run_id/area/plan_id/
    # → parent = output/run_id/area/
    # → parent.parent = output/run_id/
    # → parent.parent.parent = output/
    # → parent.parent.parent.parent = new/runner/
    # → trebuie să ajungem la jobs/run_id/
    
    # Fix corect:
    output_root = work_dir.parent.parent  # output/run_id/
    job_root = output_root.parent.parent / "jobs" / run_id  # new/runner/jobs/run_id/
    
    metadata_file = job_root / "plan_metadata" / f"{original_name}.json"
    
    if not metadata_file.exists():
        return AreaJobResult(
            plan_id=plan.plan_id,
            work_dir=work_dir,
            success=False,
            message=f"Nu găsesc {metadata_file.name} în {metadata_file.parent}"
        )
    
    # 2. Walls measurements
    perimeter_dir = work_dir.parent.parent / "perimeter" / plan.plan_id
    walls_json = perimeter_dir / "walls_measurements_gemini.json"
    
    if not walls_json.exists():
        return AreaJobResult(
            plan_id=plan.plan_id,
            work_dir=work_dir,
            success=False,
            message=f"Nu găsesc {walls_json.name}"
        )
    
    # 3. Openings (uși/ferestre)
    measure_dir = work_dir.parent.parent / "measure_objects" / plan.plan_id
    openings_json = measure_dir / "openings_all.json"
    measurements_json = measure_dir / "openings_measurements_gemini.json"
    
    if not openings_json.exists():
        return AreaJobResult(
            plan_id=plan.plan_id,
            work_dir=work_dir,
            success=False,
            message=f"Nu găsesc {openings_json.name}"
        )
    
    try:
        print(
            f"[{STAGE_NAME}] ({index}/{total}) {plan.plan_id} → calculate areas "
            f"(cwd={work_dir})",
            flush=True,
        )
        
        # ==========================================
        # LOAD DATA
        # ==========================================
        
        with open(metadata_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        
        with open(walls_json, "r", encoding="utf-8") as f:
            walls_data = json.load(f)
        
        with open(openings_json, "r", encoding="utf-8") as f:
            openings_data = json.load(f)
        
        # Extrage floor_type și house_area
        floor_class = metadata.get("floor_classification", {})
        floor_type = floor_class.get("floor_type", "unknown")
        
        house_area_m2 = floor_class.get("estimated_area_m2")
        
        if house_area_m2 is None:
            return AreaJobResult(
                plan_id=plan.plan_id,
                work_dir=work_dir,
                success=False,
                message="Nu găsesc estimated_area_m2 în metadata"
            )
        
        # Extrage aria scării (dacă există)
        stairs_area_m2 = None
        if measurements_json.exists():
            with open(measurements_json, "r", encoding="utf-8") as f:
                meas_data = json.load(f)
            
            stairs_meas = meas_data.get("measurements", {}).get("stairs")
            if stairs_meas:
                stairs_area_m2 = float(stairs_meas.get("total_area_m2", 0.0))
        
        # ==========================================
        # CALCUL ARII
        # ==========================================
        
        result = calculate_areas_for_plan(
            plan_id=plan.plan_id,
            floor_type=floor_type,
            is_single_plan=is_single_plan,
            house_area_m2=float(house_area_m2),
            walls_measurements=walls_data,
            openings_all=openings_data,
            stairs_area_m2=stairs_area_m2
        )
        
        # Add metadata
        result["meta"] = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "stage": STAGE_NAME
        }
        
        # ==========================================
        # SAVE RESULT
        # ==========================================
        
        output_file = work_dir / "areas_calculated.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"       📄 Salvat: {output_file.name}")
        
        # ==========================================
        # SUMMARY
        # ==========================================
        
        walls = result["walls"]
        surfaces = result["surfaces"]
        
        msg_parts = []
        msg_parts.append(f"Walls: I={walls['interior']['net_area_m2']:.1f}m², E={walls['exterior']['net_area_m2']:.1f}m²")
        msg_parts.append(f"Floor={surfaces['floor_m2']:.1f}m², Ceiling={surfaces['ceiling_m2']:.1f}m²")
        
        if surfaces.get("foundation_m2"):
            msg_parts.append(f"Foundation={surfaces['foundation_m2']:.1f}m²")
        if surfaces.get("roof_m2"):
            msg_parts.append(f"Roof={surfaces['roof_m2']:.1f}m²")
        
        message = " | ".join(msg_parts)
        
        return AreaJobResult(
            plan_id=plan.plan_id,
            work_dir=work_dir,
            success=True,
            message=message,
            result_data=result
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return AreaJobResult(
            plan_id=plan.plan_id,
            work_dir=work_dir,
            success=False,
            message=f"Eroare: {e}"
        )


def run_area_for_run(run_id: str, max_parallel: int | None = None) -> List[AreaJobResult]:
    """
    Punct de intrare pentru etapa „area" (calcul arii complete).
    
    Output-uri:
      new/runner/output/<RUN_ID>/area/<plan_id>/areas_calculated.json
      new/runner/output/<RUN_ID>/area/areas_summary.json  ← AGREGAT multi-plan
    """
    try:
        plans: List[PlanInfo] = load_plan_infos(run_id, stage_name=STAGE_NAME)
    except PlansListError as e:
        print(f"❌ [{STAGE_NAME}] {e}")
        return []
    
    total = len(plans)
    is_single_plan = (total == 1)
    
    print(f"\n📌 [{STAGE_NAME}] {total} plan{'uri' if total > 1 else ''} găsit{'e' if total > 1 else ''} pentru RUN_ID={run_id}")
    
    if is_single_plan:
        print(f"   ℹ️  Un singur plan → tratăm ca ground_floor + top_floor simultan\n")
    else:
        print(f"   ℹ️  Multi-plan → aplicăm logica per etaj\n")
    
    if max_parallel is None:
        cpu_count = os.cpu_count() or 4
        max_parallel = min(cpu_count, total)
    
    print(f"⚙️  [{STAGE_NAME}] rulez cu max_parallel = {max_parallel}\n", flush=True)
    
    results: List[AreaJobResult] = []
    
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = {
            executor.submit(
                _run_for_single_plan,
                run_id,
                idx,
                total,
                plan,
                is_single_plan
            ): plan
            for idx, plan in enumerate(plans, start=1)
        }
        
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            status = "✅" if res.success else "❌"
            print(
                f"{status} [{STAGE_NAME}] {res.plan_id} → {res.message[:250]}",
                flush=True,
            )
    
    failed = [r for r in results if not r.success]
    if failed:
        print(f"\n⚠️ [{STAGE_NAME}] unele planuri au eșuat:")
        for r in failed:
            print(f"   - {r.plan_id}: {r.message[:300]}")
    else:
        print(f"\n✅ [{STAGE_NAME}] toate planurile au trecut etapa area.")
    
    # ==========================================
    # AGREGARE MULTI-PLAN
    # ==========================================
    
    successful_results = [r.result_data for r in results if r.success and r.result_data]
    
    if len(successful_results) > 1:
        print(f"\n📊 Agregare rezultate multi-plan ({len(successful_results)} planuri)...")
        
        summary = aggregate_multi_plan_areas(successful_results)
        
        # Salvează summary
        output_root = Path(f"new/runner/output/{run_id}") / STAGE_NAME
        summary_file = output_root / "areas_summary.json"
        
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"       📄 Summary salvat: {summary_file}")
        
        # Afișare rezumat
        print(f"\n{'─'*70}")
        print("📊 REZUMAT ARII TOTALE:")
        print(f"{'─'*70}")
        print(f"  Fundație: {summary['surfaces']['foundation_m2']:.2f} m²")
        print(f"  Podele total: {summary['surfaces']['floor_total_m2']:.2f} m²")
        print(f"  Tavane total: {summary['surfaces']['ceiling_total_m2']:.2f} m²")
        print(f"  Acoperiș: {summary['surfaces']['roof_m2']:.2f} m²")
        print(f"  Pereți interiori net: {summary['walls']['interior']['net_total_m2']:.2f} m²")
        print(f"  Pereți exteriori net: {summary['walls']['exterior']['net_total_m2']:.2f} m²")
        print(f"{'─'*70}")
    
    # Afișare rezumat per plan
    print(f"\n{'─'*70}")
    print("📏 ARII PER PLAN:")
    print(f"{'─'*70}")
    for r in results:
        if r.success:
            print(f"  {r.plan_id}: {r.message}")
    print(f"{'─'*70}\n")
    
    return results