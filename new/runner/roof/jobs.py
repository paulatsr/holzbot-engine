# new/runner/roof/jobs.py
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List

from ..config.settings import (
    load_plan_infos,
    PlansListError,
    PlanInfo,
)

from .calculator import calculate_roof_price


STAGE_NAME = "roof"


@dataclass
class RoofJobResult:
    plan_id: str
    work_dir: Path
    success: bool
    message: str
    result_data: dict | None = None


def _load_frontend_data(job_root: Path) -> dict | None:
    frontend_file = job_root / "frontend_data.json"
    if not frontend_file.exists():
        return None
    try:
        with open(frontend_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _run_for_single_plan(
    run_id: str,
    index: int,
    total: int,
    plan: PlanInfo,
    frontend_data: dict | None,
    total_floors: int  # Parametru nou pentru calcul burlane
) -> RoofJobResult:
    """
    Calculează prețul acoperișului pentru un singur plan.
    """
    work_dir = plan.stage_work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    
    # INPUT FILES
    area_dir = work_dir.parent.parent / "area" / plan.plan_id
    area_json = area_dir / "areas_calculated.json"
    
    if not area_json.exists():
        return RoofJobResult(plan.plan_id, work_dir, False, f"Nu găsesc {area_json.name}")
    
    perimeter_dir = work_dir.parent.parent / "perimeter" / plan.plan_id
    perimeter_json = perimeter_dir / "walls_measurements_gemini.json"
    
    try:
        print(f"[{STAGE_NAME}] ({index}/{total}) {plan.plan_id} → calculate roof price", flush=True)
        
        with open(area_json, "r", encoding="utf-8") as f:
            area_data = json.load(f)
        
        surfaces = area_data.get("surfaces", {})
        
        # Aria brută a casei (pentru calculul ariei extinse cu streașină)
        roof_area_m2 = surfaces.get("roof_m2") 
        
        # Aria netă a tavanului (pentru izolație)
        # Dacă planul nu e top_floor, ceiling_m2 va fi calculat totuși în area.py
        # Dar dacă roof_area_m2 e None, înseamnă că nu e top_floor și ieșim.
        ceiling_area_m2 = surfaces.get("ceiling_m2")
        
        if roof_area_m2 is None or roof_area_m2 <= 0:
            return RoofJobResult(
                plan_id=plan.plan_id,
                work_dir=work_dir,
                success=False,
                message="Acoperișul nu e calculat pentru acest plan (nu e top_floor?)"
            )
            
        # Fallback dacă ceiling_area_m2 lipsește (dar nu ar trebui)
        if ceiling_area_m2 is None:
            ceiling_area_m2 = roof_area_m2
        
        perimeter_m = None
        if perimeter_json.exists():
            with open(perimeter_json, "r", encoding="utf-8") as f:
                perim_data = json.load(f)
            perimeter_m = perim_data.get("estimations", {}).get("average_result", {}).get("total_perimeter_meters")
        
        # EXTRAGE INPUT FRONTEND
        roof_type_user = "Două ape"
        material_user = "Țiglă"
        if frontend_data:
            roof_type_user = frontend_data.get("tipAcoperis", roof_type_user)
            material_user = frontend_data.get("materialAcoperis", material_user)
        
        # CALCUL PREȚ
        result = calculate_roof_price(
            house_area_m2=float(roof_area_m2),
            ceiling_area_m2=float(ceiling_area_m2),
            perimeter_m=float(perimeter_m) if perimeter_m else None,
            roof_type_user=roof_type_user,
            material_user=material_user,
            frontend_data=frontend_data,
            total_floors=total_floors
        )
        
        result["plan_id"] = plan.plan_id
        
        output_file = work_dir / "roof_estimation.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        roof_info = result["inputs"]["roof_type"]
        final_cost = result["roof_final_total_eur"]
        
        return RoofJobResult(
            plan_id=plan.plan_id,
            work_dir=work_dir,
            success=True,
            message=f"Tip: {roof_info['matched_name_de']} | Cost: {final_cost:,.0f} EUR",
            result_data=result
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return RoofJobResult(plan.plan_id, work_dir, False, f"Eroare: {e}")


def run_roof_for_run(run_id: str, max_parallel: int | None = None) -> List[RoofJobResult]:
    try:
        plans = load_plan_infos(run_id, stage_name=STAGE_NAME)
    except PlansListError as e:
        print(f"❌ [{STAGE_NAME}] {e}")
        return []
    
    total = len(plans)
    job_root = Path(f"new/runner/jobs/{run_id}")
    frontend_data = _load_frontend_data(job_root)
    
    print(f"\n⚙️  [{STAGE_NAME}] Calcul acoperiș pentru {total} planuri (total_floors={total})...")
    
    if max_parallel is None:
        cpu_count = os.cpu_count() or 4
        max_parallel = min(cpu_count, total)
    
    results: List[RoofJobResult] = []
    
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = {
            executor.submit(
                _run_for_single_plan,
                run_id,
                idx,
                total,
                plan,
                frontend_data,
                total  # Trimitem numărul total de planuri ca număr de etaje
            ): plan
            for idx, plan in enumerate(plans, start=1)
        }
        
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            status = "✅" if res.success else "❌"
            print(f"{status} [{STAGE_NAME}] {res.plan_id} → {res.message[:100]}")
    
    return results