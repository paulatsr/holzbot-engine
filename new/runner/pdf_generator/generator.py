# generator.py - BAZAT PE offer_pdf.py cu adaptări MINIME pentru datele tale
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
import random

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen.canvas import Canvas

from PIL import Image as PILImage, ImageEnhance, ImageOps

# ---------- FONTS ----------
FONTS_DIR = Path(__file__).parent.parent / "pdf_assets" / "fonts"
FONT_REG = FONTS_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONTS_DIR / "DejaVuSans-Bold.ttf"
BASE_FONT, BOLD_FONT = "DejaVuSans", "DejaVuSans-Bold"

try:
    if FONT_REG.exists() and FONT_BOLD.exists():
        pdfmetrics.registerFont(TTFont(BASE_FONT, str(FONT_REG)))
        pdfmetrics.registerFont(TTFont(BOLD_FONT, str(FONT_BOLD)))
except Exception:
    BASE_FONT, BOLD_FONT = "Helvetica", "Helvetica-Bold"

# ---------- COMPANY INFO ----------
COMPANY = {
    "name": "Chiemgauer Holzhaus",
    "legal": "LSP Holzbau GmbH & Co KG",
    "addr_lines": ["Seiboldsdorfer Mühle 1a", "83278 Traunstein"],
    "phone": "+49 (0) 861 / 166 192 0",
    "fax": "+49 (0) 861 / 166 192 20",
    "email": "info@chiemgauer-holzhaus.de",
    "web": "www.chiemgauer-holzhaus.de",
}

def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="H1", fontName=BOLD_FONT, fontSize=12, leading=22, spaceAfter=6))
    s.add(ParagraphStyle(name="H2", fontName=BOLD_FONT, fontSize=12.5, leading=17, spaceBefore=10, spaceAfter=6))
    s.add(ParagraphStyle(name="Body", fontName=BASE_FONT, fontSize=10, leading=14, spaceAfter=4))
    s.add(ParagraphStyle(name="Small", fontName=BASE_FONT, fontSize=7.2, leading=9.2))
    s.add(ParagraphStyle(name="Cell", fontName=BASE_FONT, fontSize=9.5, leading=12))
    s.add(ParagraphStyle(name="CellBold", fontName=BOLD_FONT, fontSize=9.5, leading=12))
    s.add(ParagraphStyle(name="CellSmall", fontName=BASE_FONT, fontSize=9, leading=11))
    return s

def P(text, style_name="Cell"):
    return Paragraph((text or "").replace("\n", "<br/>"), _styles()[style_name])

def _money(x):
    try:
        v = float(x)
        return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " €"
    except:
        return "—"

def _fmt_m2(v):
    try:
        v = float(v)
        return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " m²"
    except:
        return "—"

# ---------- CANVAS DECOR (EXACT ca în offer_pdf.py) ----------
def _draw_ribbon(canv: Canvas):
    canv.saveState()
    x, y = 18*mm, A4[1]-23*mm
    w, h = A4[0]-36*mm, 9*mm
    canv.setFillColor(colors.HexColor("#1c1c1c"))
    canv.rect(x, y, w, h, stroke=0, fill=1)
    canv.setFillColor(colors.white)
    canv.setFont(BOLD_FONT, 10)
    canv.drawString(x+6*mm, y+2.35*mm, "ANGEBOT – UNVERBINDLICHE KOSTENSCHÄTZUNG (RICHTWERT) ±10 %")
    canv.restoreState()

def _draw_firstpage_right_box(canv: Canvas, offer_no: str, handler: str):
    canv.saveState()
    box_x = A4[0]-18*mm-65*mm
    box_y = A4[1]-62*mm
    cw = 65*mm
    row_h = 8.2*mm
    rows = [
        ("Datum", datetime.now().strftime("%d.%m.%Y")),
        ("Bearbeiter", handler or "Florian Siemer"),
        ("Fibu-Info", "—"),
        ("Auftrag", offer_no),
    ]
    canv.setFont(BASE_FONT, 9)
    canv.setStrokeColor(colors.black)
    canv.rect(box_x, box_y - row_h*len(rows), cw, row_h*len(rows), stroke=1, fill=0)
    for i, (k, v) in enumerate(rows):
        y = box_y - (i+1)*row_h + 2.6*mm
        canv.drawString(box_x+3*mm, y, k)
        canv.drawRightString(box_x+cw-3*mm, y, v)
    canv.restoreState()

def _first_page_canvas(offer_no: str, handler: str):
    def _inner(canv: Canvas, doc):
        _draw_ribbon(canv)
        _draw_firstpage_right_box(canv, offer_no, handler)
    return _inner

def _noop(canv, doc):
    pass

# ---------- CONTENT BLOCKS ----------
def _header_block(story, styles, offer_no: str, client: dict):
    left_lines = [
        COMPANY["legal"],
        *COMPANY["addr_lines"],
        "",
        f"Tel. {COMPANY['phone']}",
        f"Fax {COMPANY['fax']}",
        "",
        COMPANY["email"],
        COMPANY["web"],
    ]
    left_par = Paragraph("<br/>".join(left_lines), styles["Small"])
    right_par = Paragraph("", styles["Small"])

    data = [[left_par, right_par]]
    tbl = Table(data, colWidths=[95*mm, A4[0]-36*mm-95*mm])
    tbl.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP")]))

    story.append(Spacer(1, 34*mm))
    story.append(tbl)
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(f"Angebot • Nr.: {offer_no}", styles["H1"]))
    story.append(Spacer(1, 3*mm))
    story.append(_client_info_block(client))
    story.append(Spacer(1, 6*mm))

def _client_info_block(client: dict):
    name = (client.get("name") or "—").strip()
    city = (client.get("city") or "—").strip()
    phone = (client.get("phone") or "—").strip()
    email = (client.get("email") or "—").strip()
    proj = (client.get("project_label") or "—").strip()

    lines = [
        f"<b>Kundin/Kunde:</b> {name}",
        f"<b>Ort:</b> {city}",
        f"<b>Telefon:</b> {phone}",
        f"<b>E-Mail:</b> {email}",
        f"<b>Projekt:</b> {proj}",
    ]
    return Paragraph("<br/>".join(lines), _styles()["Cell"])

def _intro(story, styles, client):
    story.append(Paragraph("Angebot für Ihr Chiemgauer Massivholzhaus als Komplettmontage", styles["H2"]))
    story.append(Paragraph("Sehr geehrte Kundschaft,", styles["Body"]))
    story.append(Paragraph("vielen Dank für Ihre Anfrage. Gerne haben wir für Sie das nachstehende Angebot ausgearbeitet.", styles["Body"]))
    story.append(Paragraph("Bitte setzen Sie sich bei Rückfragen jederzeit mit uns in Verbindung, um das Angebot detaillierter zu besprechen.", styles["Body"]))
    story.append(Spacer(1, 6*mm))

def _table_openings_detailed(story, styles, pricing_data: dict):
    """Tabel DETALIAT cu toate ușile și ferestrele"""
    openings = pricing_data.get("breakdown", {}).get("openings", {})
    items = openings.get("items", []) or openings.get("detailed_items", [])
    
    if not items:
        return
    
    story.append(Paragraph(f"Öffnungen (Türen / Fenster) – {len(items)} Elemente", styles["H2"]))
    
    head = [P("ID","CellBold"), P("Typ","CellBold"), P("Ort","CellBold"), 
            P("Material","CellBold"), P("Maße","CellBold"), 
            P("Fläche","CellBold"), P("Preis","CellBold")]
    
    data = []
    for it in items:
        data.append([
            P(str(it.get("id", "—"))),
            P(str(it.get("type", "—")).title()),
            P(it.get("location", "—")),
            P(it.get("material", "—")),
            P(it.get("dimensions_m", "—"), "CellSmall"),
            P(f"{it.get('area_m2', 0):.2f}"),
            P(_money(it.get("total_cost", 0)), "CellBold"),
        ])
    
    tbl = Table([head] + data, colWidths=[12*mm, 22*mm, 18*mm, 18*mm, 22*mm, 18*mm, 25*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (5,1), (-1,-1), "RIGHT"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

def _table_structure_walls(story, styles, pricing_data: dict):
    """Tabel pereți cu detalii"""
    walls = pricing_data.get("breakdown", {}).get("structure_walls", {})
    items = walls.get("items", []) or walls.get("detailed_items", [])
    
    if not items:
        return
    
    story.append(Paragraph("Tragstruktur – Wände", styles["H2"]))
    
    head = [P("Beschreibung","CellBold"), P("Fläche","CellBold"), P("Preis/m²","CellBold"), P("Gesamt","CellBold")]
    data = []
    
    for it in items:
        data.append([
            P(it.get("name", "—")),
            P(_fmt_m2(it.get("area_m2", 0))),
            P(_money(it.get("unit_price", 0)), "CellSmall"),
            P(_money(it.get("cost", 0)), "CellBold"),
        ])
    
    data.append([P("SUMME","CellBold"), P(""), P(""), P(_money(walls.get("total_cost", 0)),"CellBold")])
    
    tbl = Table([head] + data, colWidths=[70*mm, 35*mm, 30*mm, 35*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#e8e8e8")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

def _table_floors_ceilings(story, styles, pricing_data: dict):
    """Tabel planșee & tavane"""
    fc = pricing_data.get("breakdown", {}).get("floors_ceilings", {})
    items = fc.get("items", []) or fc.get("detailed_items", [])
    
    if not items:
        return
    
    story.append(Paragraph("Geschossdecken & Decken", styles["H2"]))
    
    head = [P("Element","CellBold"), P("Fläche","CellBold"), P("Preis/m²","CellBold"), P("Gesamt","CellBold")]
    data = []
    
    for it in items:
        data.append([
            P(it.get("name", "—")),
            P(_fmt_m2(it.get("area_m2", 0))),
            P(_money(it.get("unit_price", 0)), "CellSmall"),
            P(_money(it.get("cost", 0)), "CellBold"),
        ])
    
    data.append([P("SUMME","CellBold"), P(""), P(""), P(_money(fc.get("total_cost", 0)),"CellBold")])
    
    tbl = Table([head] + data, colWidths=[70*mm, 35*mm, 30*mm, 35*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#e8e8e8")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

def _table_roof(story, styles, pricing_data: dict):
    """Tabel acoperiș detaliat"""
    roof = pricing_data.get("breakdown", {}).get("roof", {})
    items = roof.get("items", []) or roof.get("detailed_items", [])
    
    if not items:
        return
    
    story.append(Paragraph("Dach – Komponenten", styles["H2"]))
    
    head = [P("Komponente","CellBold"), P("Details","CellBold"), P("Preis","CellBold")]
    data = []
    
    for it in items:
        data.append([
            P(it.get("name", "—")),
            P(it.get("details", ""), "CellSmall"),
            P(_money(it.get("cost", 0)), "CellBold"),
        ])
    
    data.append([P("SUMME DACH","CellBold"), P(""), P(_money(roof.get("total_cost", 0)),"CellBold")])
    
    tbl = Table([head] + data, colWidths=[50*mm, 70*mm, 40*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#e8e8e8")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (2,1), (2,-1), "RIGHT"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

def _table_finishes(story, styles, pricing_data: dict):
    """Tabel finisaje"""
    finishes = pricing_data.get("breakdown", {}).get("finishes", {})
    items = finishes.get("items", []) or finishes.get("detailed_items", [])
    
    if not items:
        return
    
    story.append(Paragraph("Oberflächen & Finishes", styles["H2"]))
    
    head = [P("Finisaj","CellBold"), P("Fläche","CellBold"), P("Preis/m²","CellBold"), P("Gesamt","CellBold")]
    data = []
    
    for it in items:
        data.append([
            P(it.get("name", "—")),
            P(_fmt_m2(it.get("area_m2", 0))),
            P(_money(it.get("unit_price", 0)), "CellSmall"),
            P(_money(it.get("cost", 0)), "CellBold"),
        ])
    
    data.append([P("SUMME","CellBold"), P(""), P(""), P(_money(finishes.get("total_cost", 0)),"CellBold")])
    
    tbl = Table([head] + data, colWidths=[70*mm, 35*mm, 30*mm, 35*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#e8e8e8")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

def _table_utilities(story, styles, pricing_data: dict):
    """Tabel utilități"""
    utilities = pricing_data.get("breakdown", {}).get("utilities", {})
    items = utilities.get("items", []) or utilities.get("detailed_items", [])
    
    if not items:
        return
    
    story.append(Paragraph("Haustechnik", styles["H2"]))
    
    head = [P("Kategorie","CellBold"), P("Fläche","CellBold"), P("Preis/m²","CellBold"), P("Gesamt","CellBold")]
    data = []
    
    for it in items:
        cat_map = {
            "electricity": "Elektro",
            "heating": "Heizung",
            "ventilation": "Lüftung",
            "sewage": "Abwasser"
        }
        cat = cat_map.get(it.get("category"), it.get("name", "—"))
        
        data.append([
            P(cat),
            P(_fmt_m2(it.get("area_m2", 0))),
            P(_money(it.get("final_price_per_m2", 0)), "CellSmall"),
            P(_money(it.get("total_cost", 0)), "CellBold"),
        ])
    
    data.append([P("SUMME","CellBold"), P(""), P(""), P(_money(utilities.get("total_cost", 0)),"CellBold")])
    
    tbl = Table([head] + data, colWidths=[70*mm, 35*mm, 30*mm, 35*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#e8e8e8")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

def _closing_blocks(story, styles):
    story.append(Paragraph("Annahmen & Einschränkungen", styles["H2"]))
    story.append(Paragraph(
        "Diese Zusammenstellung basiert auf den vorliegenden Planunterlagen sowie gängigen Ausführungsstandards für Massivholzbauten. "
        "Besondere geotechnische Voraussetzungen oder Projektänderungen können Mengen und Summen nach einer Vor-Ort-Prüfung beeinflussen.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4*mm))

def generate_complete_offer_pdf(run_id: str, output_path: Path | None = None) -> Path:
    print(f"🚀 [PDF] START: {run_id}")
    
    runner_root = Path(__file__).resolve().parents[1]
    output_root = runner_root / "output" / run_id
    if not output_root.exists():
        output_root = runner_root.parent / "output" / run_id
    
    if not output_root.exists():
        raise FileNotFoundError(f"Output: {output_root}")

    jobs_root = runner_root.parent.parent / "jobs" / run_id

    if output_path is None:
        pdf_dir = output_root / "offer_pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        output_path = pdf_dir / f"oferta_{run_id}.pdf"

    # CITIRE CLIENT - ADAPTAT pentru structura TA
    frontend_path = jobs_root / "frontend_data.json"
    if not frontend_path.exists():
        frontend_path = jobs_root / "fallback_frontend_data.json"
    
    frontend_data = {}
    if frontend_path.exists():
        with open(frontend_path, encoding="utf-8") as f:
            frontend_data = json.load(f)
    
    # STRUCTURA TA: client în subsecțiune
    client_section = frontend_data.get("client", {})
    
    client = {
        "name": client_section.get("nume", "Kunde"),
        "phone": client_section.get("telefon", "—"),
        "email": client_section.get("email", "—"),
        "city": client_section.get("localitate", "—"),
        "project_label": frontend_data.get("referinta", "Projekt"),
    }
    
    print(f"✅ [CLIENT] {client['name']} | {client['phone']}")

    # CITIRE PLANS
    plans_list_path = output_root / "plans_list.json"
    with open(plans_list_path, encoding="utf-8") as f:
        plans_list = json.load(f)
    
    plan_paths = plans_list.get("plans", [])
    plan_stems = [Path(p).stem for p in plan_paths]
    
    plans_data = []
    for stem in plan_stems:
        print(f"👉 [PLAN] {stem}")
        
        pricing_path = output_root / "pricing" / stem / "pricing_raw.json"
        if not pricing_path.exists():
            # Try with underscore
            pricing_path = output_root / "pricing" / stem.replace(" ", "_") / "pricing_raw.json"
        
        if pricing_path.exists():
            with open(pricing_path, encoding="utf-8") as f:
                pricing_data = json.load(f)
            print(f"   ✅ Total: {pricing_data.get('total_cost_eur')} EUR")
            plans_data.append({"plan_id": stem, "pricing": pricing_data})
        else:
            print(f"   ❌ Pricing missing!")

    # BUILD PDF
    offer_no = f"CHH-{datetime.now().strftime('%Y')}-{random.randint(1000,9999)}"
    handler = "Florian Siemer"
    
    styles = _styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=20*mm, bottomMargin=22*mm,
        title=f"Angebot – {offer_no}",
        author=COMPANY["name"]
    )

    story = []
    _header_block(story, styles, offer_no, client)
    _intro(story, styles, client)
    
    # Per plan
    for plan_info in plans_data:
        story.append(PageBreak())
        story.append(Paragraph(f"Plan: {plan_info['plan_id']}", styles["H1"]))
        story.append(Spacer(1, 8*mm))
        
        pricing = plan_info["pricing"]
        
        _table_structure_walls(story, styles, pricing)
        _table_floors_ceilings(story, styles, pricing)
        _table_roof(story, styles, pricing)
        _table_openings_detailed(story, styles, pricing)
        _table_finishes(story, styles, pricing)
        _table_utilities(story, styles, pricing)
        
        # Total plan
        total = pricing.get("total_cost_eur", 0)
        story.append(Paragraph(f"<b>Gesamtsumme Plan: {_money(total)}</b>", styles["H1"]))
        story.append(Spacer(1, 12*mm))
    
    # Final total
    story.append(PageBreak())
    story.append(Paragraph("Gesamtkostenzusammenfassung", styles["H1"]))
    
    grand_total = sum(p["pricing"].get("total_cost_eur", 0) for p in plans_data)
    vat = grand_total * 0.19
    final = grand_total + vat
    
    story.append(Paragraph(f"Zwischensumme: {_money(grand_total)}", styles["Body"]))
    story.append(Paragraph(f"MwSt. (19%): {_money(vat)}", styles["Body"]))
    story.append(Paragraph(f"<b>ENDSUMME: {_money(final)}</b>", styles["H1"]))
    
    _closing_blocks(story, styles)

    doc.build(
        story,
        onFirstPage=_first_page_canvas(offer_no, handler),
        onLaterPages=_noop
    )

    print(f"✅ [PDF] {output_path}")
    return output_path