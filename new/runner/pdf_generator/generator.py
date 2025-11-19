# new/runner/pdf_generator/generator.py
from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime
from PIL import Image as PILImage, ImageEnhance, ImageOps

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
)

from .styles import get_styles, COLORS
from .tables import (
    P, create_client_info_table, create_plan_summary_table,
    create_walls_table, create_surfaces_table, create_openings_table,
    create_pricing_breakdown_table, create_totals_summary_table
)
from .utils import (
    safe_get, load_json_safe, get_plan_image_path
)


def _process_plan_image(img_path: Path, output_dir: Path, plan_id: str) -> Path | None:
    """
    Procesează imaginea planului (grayscale + contrast) și o salvează pentru PDF.
    """
    if not img_path or not img_path.exists():
        return None
    
    output_dir.mkdir(parents=True, exist_ok=True)
    processed_path = output_dir / f"{plan_id}_processed.png"
    
    try:
        img = PILImage.open(img_path).convert("L")  # Grayscale
        img = ImageEnhance.Brightness(img).enhance(0.9)
        img = ImageOps.autocontrast(img)
        img.save(processed_path)
        return processed_path
    except Exception as e:
        print(f"⚠️ Eroare procesare imagine {plan_id}: {e}")
        return None


def _add_plan_section(story, styles, plan_id: str, plan_data: dict, 
                       pricing_data: dict, openings_data: list,
                       img_path: Path | None):
    """
    Adaugă o secțiune completă pentru un plan individual.
    """
    # Titlu plan
    story.append(PageBreak())
    story.append(Paragraph(f"Plan: {plan_id}", styles["H1"]))
    story.append(Spacer(1, 6*mm))
    
    # Imagine plan (dacă există)
    if img_path and img_path.exists():
        try:
            img = Image(str(img_path))
            img._restrictSize(A4[0] - 36*mm, 85*mm)
            story.append(img)
            story.append(Spacer(1, 8*mm))
        except Exception as e:
            print(f"⚠️ Eroare inserare imagine {plan_id}: {e}")
    
    # Rezumat plan
    story.append(Paragraph("Rezumat Plan", styles["H2"]))
    story.append(create_plan_summary_table(plan_data, plan_id))
    story.append(Spacer(1, 8*mm))
    
    # Pereți
    walls_data = plan_data.get("walls", {})
    if walls_data:
        story.append(Paragraph("Pereți (Detaliat)", styles["H2"]))
        story.append(create_walls_table(walls_data))
        story.append(Spacer(1, 8*mm))
    
    # Suprafețe
    surfaces_data = plan_data.get("surfaces", {})
    if surfaces_data:
        story.append(Paragraph("Suprafețe", styles["H2"]))
        story.append(create_surfaces_table(surfaces_data))
        story.append(Spacer(1, 8*mm))
    
    # Deschideri (uși/ferestre)
    if openings_data:
        story.append(Paragraph(f"Deschideri ({len(openings_data)} obiecte)", styles["H2"]))
        story.append(create_openings_table(openings_data))
        story.append(Spacer(1, 8*mm))
    
    # Costuri plan
    if pricing_data:
        story.append(Paragraph("Breakdown Costuri Plan", styles["H2"]))
        story.append(create_pricing_breakdown_table(pricing_data))
        story.append(Spacer(1, 10*mm))


def generate_complete_offer_pdf(run_id: str, output_path: Path | None = None) -> Path:
    """
    Generează PDF-ul complet de ofertă cu TOATE detaliile din pipeline.
    
    Args:
        run_id: ID-ul run-ului (ex: "segmentation_job_20251119_...")
        output_path: Path custom pentru PDF (opțional)
    
    Returns:
        Path către PDF-ul generat
    """
    
    # ==========================================
    # 1. DETECTARE PATHS
    # ==========================================
    runner_root = Path(__file__).resolve().parents[2]  # new/runner/
    output_root = runner_root / "output" / run_id
    jobs_root = runner_root.parent.parent / "jobs" / run_id  # jobs/run_id/
    
    if not output_root.exists():
        raise FileNotFoundError(f"Output directory nu există: {output_root}")
    
    # Output PDF
    if output_path is None:
        pdf_dir = output_root / "offer_pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        output_path = pdf_dir / f"oferta_{run_id}.pdf"
    
    print(f"\n{'='*70}")
    print(f"📄 Generare PDF Ofertă Detaliată")
    print(f"{'='*70}")
    print(f"Run ID: {run_id}")
    print(f"Output: {output_path}")
    print(f"{'='*70}\n")
    
    # ==========================================
    # 2. LOAD DATE FRONTEND (client info)
    # ==========================================
    frontend_data = load_json_safe(jobs_root / "frontend_data.json")
    
    client_data = {
        "nume": frontend_data.get("nume", "Client Necunoscut"),
        "telefon": frontend_data.get("telefon", "—"),
        "email": frontend_data.get("email", "—"),
        "localitate": frontend_data.get("localitate", "—"),
        "referinta": frontend_data.get("referinta", "Proiect Casă din Lemn")
    }
    
    # ==========================================
    # 3. LOAD PLANS_LIST
    # ==========================================
    runs_dir = runner_root.parent.parent / "runs" / run_id
    plans_list = load_json_safe(runs_dir / "plans_list.json")
    plan_paths = plans_list.get("plans", [])
    
    if not plan_paths:
        raise ValueError("Nu există planuri în plans_list.json")
    
    # Extract plan IDs
    plan_ids = []
    for p in plan_paths:
        p_path = Path(p)
        # Ex: /path/to/output/run_id/segmenter/plan_01_cluster/plan.jpg
        # → plan_id = plan_01_cluster
        if p_path.parent.name.startswith("plan_"):
            plan_ids.append(p_path.parent.name)
        else:
            plan_ids.append(p_path.stem)
    
    print(f"📋 Planuri detectate: {len(plan_ids)}")
    for pid in plan_ids:
        print(f"   • {pid}")
    
    # ==========================================
    # 4. LOAD DATE PER PLAN
    # ==========================================
    plans_data = []
    
    for plan_id in plan_ids:
        plan_info = {
            "plan_id": plan_id,
            "area": None,
            "pricing": None,
            "openings": [],
            "image_path": None
        }
        
        # Area
        area_json = output_root / "area" / plan_id / "areas_calculated.json"
        if area_json.exists():
            plan_info["area"] = load_json_safe(area_json)
        
        # Pricing
        pricing_json = output_root / "pricing" / plan_id / "pricing_raw.json"
        if pricing_json.exists():
            plan_info["pricing"] = load_json_safe(pricing_json)
        
        # Openings
        openings_json = output_root / "measure_objects" / plan_id / "openings_all.json"
        if openings_json.exists():
            plan_info["openings"] = load_json_safe(openings_json)
        
        # Image
        # Caută în classified/blueprints/
        img = get_plan_image_path(plan_id, jobs_root / "segmentation")
        if img:
            plan_info["image_path"] = img
        
        plans_data.append(plan_info)
    
    # ==========================================
    # 5. LOAD SUMMARY (dacă există areas_summary.json)
    # ==========================================
    summary_area = load_json_safe(output_root / "area" / "areas_summary.json")
    
    # ==========================================
    # 6. CREEARE PDF
    # ==========================================
    styles = get_styles()
    
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18*mm,
        rightMargin=18*mm,
        topMargin=20*mm,
        bottomMargin=20*mm,
        title=f"Ofertă Detaliată - {client_data['referinta']}",
        author="Holzbot Engine"
    )
    
    story = []
    
    # ==========================================
    # PAGINA 1: COVER & CLIENT INFO
    # ==========================================
    story.append(Spacer(1, 30*mm))
    story.append(Paragraph("OFERTĂ DETALIATĂ", styles["Title"]))
    story.append(Paragraph(f"Proiect: {client_data['referinta']}", styles["H1"]))
    story.append(Spacer(1, 10*mm))
    
    story.append(Paragraph("Informații Client", styles["H2"]))
    story.append(create_client_info_table(client_data))
    story.append(Spacer(1, 10*mm))
    
    story.append(Paragraph(
        f"Data generării: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        styles["Body"]
    ))
    
    # ==========================================
    # PAGINA 2: REZUMAT GENERAL
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("Rezumat General Proiect", styles["H1"]))
    story.append(Spacer(1, 6*mm))
    
    if summary_area:
        story.append(Paragraph("Suprafețe Totale (Multi-Plan)", styles["H2"]))
        
        surfaces = summary_area.get("surfaces", {})
        walls = summary_area.get("walls", {})
        
        summary_text = f"""
        <b>Total Planuri:</b> {summary_area.get('total_plans', len(plans_data))}<br/>
        <b>Fundație:</b> {safe_get(surfaces, 'foundation_m2', default=0.0):.2f} m²<br/>
        <b>Podele Total:</b> {safe_get(surfaces, 'floor_total_m2', default=0.0):.2f} m²<br/>
        <b>Tavane Total:</b> {safe_get(surfaces, 'ceiling_total_m2', default=0.0):.2f} m²<br/>
        <b>Acoperiș:</b> {safe_get(surfaces, 'roof_m2', default=0.0):.2f} m²<br/>
        <b>Pereți Interiori Net:</b> {safe_get(walls, 'interior', 'net_total_m2', default=0.0):.2f} m²<br/>
        <b>Pereți Exteriori Net:</b> {safe_get(walls, 'exterior', 'net_total_m2', default=0.0):.2f} m²
        """
        
        story.append(Paragraph(summary_text, styles["Body"]))
        story.append(Spacer(1, 10*mm))
    
    # ==========================================
    # SECȚIUNI PER PLAN
    # ==========================================
    for plan_info in plans_data:
        plan_id = plan_info["plan_id"]
        area_data = plan_info["area"] or {}
        pricing_data = plan_info["pricing"] or {}
        openings_data = plan_info["openings"] or []
        img_path = plan_info["image_path"]
        
        # Procesează imaginea
        processed_img = None
        if img_path:
            processed_img = _process_plan_image(
                img_path,
                output_path.parent,
                plan_id
            )
        
        _add_plan_section(
            story,
            styles,
            plan_id,
            area_data,
            pricing_data,
            openings_data,
            processed_img
        )
    
    # ==========================================
    # PAGINA FINALĂ: TOTAL COSTURI
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("Rezumat Final Costuri", styles["H1"]))
    story.append(Spacer(1, 6*mm))
    
    # Calculează totaluri din toate planurile
    totals = {
        "foundation": 0.0,
        "structure": 0.0,
        "floors_ceilings": 0.0,
        "roof": 0.0,
        "openings": 0.0,
        "finishes": 0.0,
        "utilities": 0.0
    }
    
    for plan_info in plans_data:
        pricing = plan_info.get("pricing", {})
        breakdown = pricing.get("breakdown", {})
        
        for key in totals.keys():
            data = breakdown.get(key, {})
            totals[key] += data.get("total_cost", 0.0)
    
    story.append(create_totals_summary_table(totals))
    story.append(Spacer(1, 10*mm))
    
    # Disclaimer
    story.append(Paragraph("Notă Importantă", styles["H2"]))
    story.append(Paragraph(
        "Această ofertă este generată automat pe baza analizei planurilor arhitecturale. "
        "Prețurile sunt estimative și pot varia în funcție de condițiile reale de șantier, "
        "materiale disponibile și alte factori specifici proiectului. "
        "Pentru o ofertă finală detaliată, vă rugăm să ne contactați.",
        styles["Body"]
    ))
    
    # ==========================================
    # BUILD PDF
    # ==========================================
    doc.build(story)
    
    print(f"\n✅ PDF generat cu succes: {output_path}")
    print(f"   Mărime: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"{'='*70}\n")
    
    return output_path