from __future__ import annotations
import json
import io
from pathlib import Path
from datetime import datetime
import random

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen.canvas import Canvas

from PIL import Image as PILImage, ImageEnhance, ImageOps

from ..config.settings import load_plan_infos, PlansListError, RUNNER_ROOT, PROJECT_ROOT

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

# ---------- COMPANY & IMAGES ----------
COMPANY = {
    "name": "Chiemgauer Holzhaus",
    "legal": "LSP Holzbau GmbH & Co KG",
    "addr_lines": ["Seiboldsdorfer Mühle 1a", "83278 Traunstein"],
    "phone": "+49 (0) 861 / 166 192 0",
    "fax":   "+49 (0) 861 / 166 192 20",
    "email": "info@chiemgauer-holzhaus.de",
    "web":   "www.chiemgauer-holzhaus.de",
    "footer_left":  "Chiemgauer Holzhaus\nLSP Holzbau GmbH & Co KG\nRegistergericht Traunstein HRA Nr. 7311\nGeschäftsführer Bernhard Oeggl",
    "footer_mid":   "LSP Verwaltungs GmbH\nPersönlich haftende Gesellschafterin\nRegistergericht Traunstein HRB Nr. 13146",
    "footer_right": "Volksbank Raiffeisenbank Oberbayern Südost eG\nKto.Nr. 7 313 640  ·  BLZ 710 900 00\nIBAN: DE81 7109 0000 0007 3136 40   BIC: GENODEF1BGL   USt-ID: DE131544091",
}

IMG_IDENTITY = PROJECT_ROOT / "offer_identity.png"
IMG_LOGOS = PROJECT_ROOT / "offer_logos.png"

# ---------- STYLES ----------
def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="H1", fontName=BOLD_FONT,  fontSize=12,   leading=22, spaceAfter=10, spaceBefore=6))
    s.add(ParagraphStyle(name="H2", fontName=BOLD_FONT,  fontSize=11, leading=14, spaceBefore=12, spaceAfter=6))
    s.add(ParagraphStyle(name="Body", fontName=BASE_FONT, fontSize=10,  leading=14, spaceAfter=4))
    s.add(ParagraphStyle(name="Small", fontName=BASE_FONT, fontSize=7.2, leading=9.2))
    s.add(ParagraphStyle(name="Disclaimer", fontName=BASE_FONT, fontSize=8.5, leading=11, textColor=colors.HexColor("#333333")))
    s.add(ParagraphStyle(name="Cell", fontName=BASE_FONT, fontSize=9.5, leading=12))
    s.add(ParagraphStyle(name="CellBold", fontName=BOLD_FONT, fontSize=9.5, leading=12))
    s.add(ParagraphStyle(name="CellSmall", fontName=BASE_FONT, fontSize=9, leading=11))
    return s

def P(text, style_name="Cell"):
    return Paragraph((str(text) or "").replace("\n", "<br/>"), _styles()[style_name])

def _money(x):
    try:
        v = float(x)
        return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " €"
    except:
        return "—"

def _fmt_m2(v):
    try:
        val = float(v)
        return f"{val:,.2f} m²"
    except:
        return "—"

def _fmt_qty(v, unit=""):
    try:
        val = float(v)
        return f"{val:,.2f} {unit}"
    except:
        return "—"

# ---------- CANVAS (HEADER/FOOTER) ----------

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

def _draw_footer(canv: Canvas):
    canv.saveState()
    y = 9*mm
    colw = (A4[0]-36*mm)/3.0
    x0 = 18*mm
    canv.setFont(BASE_FONT, 6.6)
    canv.setFillColor(colors.black)
    
    for i, block in enumerate((COMPANY["footer_left"], COMPANY["footer_mid"], COMPANY["footer_right"])):
        tx = x0 + i*colw
        lines = block.split("\n")
        for idx, line in enumerate(lines):
            canv.drawString(tx, y + (len(lines)-idx-1)*3.0*mm, line)
    canv.restoreState()

def _draw_firstpage_right_box(canv: Canvas, offer_no: str, handler: str):
    canv.saveState()
    box_x = A4[0]-18*mm-65*mm
    box_y = A4[1]-62*mm
    cw = 65*mm
    row_h = 8.2*mm
    rows = [
        ("Datum", datetime.now().strftime("%d.%m.%Y")),
        ("Bearbeiter", handler),
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
        if IMG_IDENTITY.exists():
            canv.drawImage(str(IMG_IDENTITY), A4[0]-18*mm-85*mm, A4[1]-53*mm, 85*mm, 22*mm, preserveAspectRatio=True, mask='auto')
        if IMG_LOGOS.exists():
            canv.drawImage(str(IMG_LOGOS), 18*mm, A4[1]-55*mm, 80*mm, 26*mm, preserveAspectRatio=True, mask='auto', anchor='sw')
        _draw_firstpage_right_box(canv, offer_no, handler)
        _draw_footer(canv)
    return _inner

def _later_pages_canvas(canv: Canvas, doc):
    _draw_ribbon(canv)
    _draw_footer(canv)

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

    tbl = Table([[left_par, right_par]], colWidths=[95*mm, A4[0]-36*mm-95*mm])
    tbl.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP")]))

    story.append(Spacer(1, 36*mm))
    story.append(tbl)
    story.append(Spacer(1, 6*mm))
    
    story.append(Paragraph(f"Angebot • Nr.: {offer_no}", styles["H1"]))
    story.append(Spacer(1, 3*mm))
    
    story.append(_client_info_block(client))
    story.append(Spacer(1, 6*mm))

def _client_info_block(client: dict):
    name = (client.get("nume") or client.get("name") or "—").strip()
    city = (client.get("localitate") or client.get("city") or "—").strip()
    phone = (client.get("telefon") or client.get("phone") or "—").strip()
    email = (client.get("email") or "—").strip()
    proj = (client.get("referinta") or client.get("project_label") or "—").strip()

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
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "Hinweis/Haftungsausschluss: Dieses Dokument stellt eine unverbindliche, orientierende Kostenschätzung dar und ist kein offizielles Angebot im rechtlichen Sinne.",
        styles["Disclaimer"]
    ))
    story.append(Spacer(1, 6*mm))

# ---------- TABLES ----------

def _table_standard(story, styles, title, data_dict):
    items = data_dict.get("items", []) or data_dict.get("detailed_items", [])
    if not items:
        return

    story.append(Paragraph(title, styles["H2"]))
    head = [P("Element", "CellBold"), P("Fläche", "CellBold"), P("Preis/m²", "CellBold"), P("Wert", "CellBold")]
    data = []

    for it in items:
        data.append([
            P(it.get("name", "—")),
            P(_fmt_m2(it.get("area_m2", 0))), 
            P(_money(it.get("unit_price", 0)), "CellSmall"),
            P(_money(it.get("cost", 0)), "CellBold"),
        ])
    
    data.append([P("SUMME", "CellBold"), "", "", P(_money(data_dict.get("total_cost", 0)), "CellBold")])
    
    tbl = Table([head] + data, colWidths=[75*mm, 40*mm, 32*mm, 38*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 4*mm))

def _table_roof_quantities(story, styles, pricing_data: dict):
    """Tabel Acoperiș cu cantități. FĂRĂ PEREȚI SUPLIMENTARI (mutați la pereți exteriori)."""
    roof = pricing_data.get("breakdown", {}).get("roof", {})
    items = roof.get("items", []) or roof.get("detailed_items", [])
    
    # Filtrăm pereții suplimentari pentru afișare
    display_items = [it for it in items if "extra_walls" not in it.get("category", "")]
    
    if not display_items:
        return
    
    # Recalculăm totalul afișat (scăzând pereții mutați)
    visible_total = sum(it.get("cost", 0) for it in display_items)

    story.append(Paragraph("Dach – Detail", styles["H2"]))
    
    head = [P("Komponente", "CellBold"), P("Bemerkungen", "CellBold"), P("Einheit", "CellBold"), P("Preis", "CellBold")]
    data = []
    
    for it in display_items:
        qty = it.get("quantity", 0)
        unit = it.get("unit", "")
        qty_str = _fmt_qty(qty, unit) if qty > 0 else "—"
        
        data.append([
            P(it.get("name", "—")),
            P(it.get("details", ""), "CellSmall"),
            P(qty_str, "CellSmall"),
            P(_money(it.get("cost", 0)), "CellBold"),
        ])
    
    data.append([P("SUMME DACH", "CellBold"), "", "", P(_money(visible_total), "CellBold")])
    
    tbl = Table([head] + data, colWidths=[55*mm, 70*mm, 24*mm, 32*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (2,1), (3,-1), "RIGHT"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 4*mm))

def _table_global_openings(story, styles, all_openings: list):
    if not all_openings: return 0.0

    story.append(PageBreak())
    story.append(Paragraph("Zusammenfassung Öffnungen (Fenster & Türen)", styles["H1"]))
    
    agg = {
        "windows": {"n": 0, "eur": 0.0},
        "doors_int": {"n": 0, "eur": 0.0},
        "doors_ext": {"n": 0, "eur": 0.0}
    }
    
    for it in all_openings:
        t = str(it.get("type", "")).lower()
        cost = float(it.get("total_cost", 0))
        
        if "window" in t:
            agg["windows"]["n"] += 1
            agg["windows"]["eur"] += cost
        elif "door" in t:
            if "exterior" in t or "entrance" in t or "outside" in str(it.get("location", "")).lower():
                agg["doors_ext"]["n"] += 1
                agg["doors_ext"]["eur"] += cost
            else:
                agg["doors_int"]["n"] += 1
                agg["doors_int"]["eur"] += cost

    def avg(total, n): return total / n if n > 0 else 0.0

    head = [P("Kategorie", "CellBold"), P("Stück", "CellBold"), P("Preis/Stk.", "CellBold"), P("Gesamt", "CellBold")]
    data = []
    
    # Ordine specifică: Ferestre, Uși Ext, Uși Int (separate)
    if agg["windows"]["n"] > 0:
        data.append([P("Fenster"), P(str(agg["windows"]["n"])), P(_money(avg(agg["windows"]["eur"], agg["windows"]["n"]))), P(_money(agg["windows"]["eur"]))])
    if agg["doors_ext"]["n"] > 0:
        data.append([P("Außentüren"), P(str(agg["doors_ext"]["n"])), P(_money(avg(agg["doors_ext"]["eur"], agg["doors_ext"]["n"]))), P(_money(agg["doors_ext"]["eur"]))])
    if agg["doors_int"]["n"] > 0:
        data.append([P("Innentüren"), P(str(agg["doors_int"]["n"])), P(_money(avg(agg["doors_int"]["eur"], agg["doors_int"]["n"]))), P(_money(agg["doors_int"]["eur"]))])
    
    total_eur = agg["doors_int"]["eur"] + agg["doors_ext"]["eur"] + agg["windows"]["eur"]
    data.append([P("SUMME ÖFFNUNGEN", "CellBold"), "", "", P(_money(total_eur), "CellBold")])

    tbl = Table([head] + data, colWidths=[68*mm, 26*mm, 34*mm, 40*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))
    return total_eur

def _table_global_utilities(story, styles, all_utilities: list):
    """Tabel global utilități (instalații) - toate planurile însumate."""
    if not all_utilities: return 0.0

    story.append(Paragraph("Zusammenfassung Haustechnik & Installationen", styles["H1"]))
    
    agg = {"electricity": 0.0, "sewage": 0.0, "heating": 0.0, "ventilation": 0.0}
    total_util = 0.0
    
    for it in all_utilities:
        cat = it.get("category", "")
        cost = it.get("total_cost", 0.0)
        total_util += cost
        if cat in agg:
            agg[cat] += cost
        else:
            agg.setdefault("other", 0.0)
            agg["other"] += cost
            
    head = [P("Gewerk / Kategorie", "CellBold"), P("Gesamtpreis", "CellBold")]
    data = []
    
    label_map = {
        "electricity": "Elektroinstallation",
        "sewage": "Sanitär & Abwasser",
        "heating": "Heizungstechnik",
        "ventilation": "Lüftung",
        "other": "Sonstige"
    }
    
    for k, v in agg.items():
        if v > 0:
            data.append([P(label_map.get(k, k.title())), P(_money(v))])
            
    data.append([P("SUMME HAUSTECHNIK", "CellBold"), P(_money(total_util), "CellBold")])
    
    tbl = Table([head] + data, colWidths=[120*mm, 50*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))
    return total_util

def _closing_blocks(story, styles):
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("Annahmen & Einschränkungen", styles["H2"]))
    story.append(Paragraph(
        "Diese Zusammenstellung basiert auf den vorliegenden Planunterlagen sowie gängigen Ausführungsstandards für Massivholzbauten. "
        "Besondere geotechnische Voraussetzungen oder Projektänderungen können Mengen und Summen nach einer Vor-Ort-Prüfung beeinflussen.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "Termine und Abläufe stehen unter dem Vorbehalt der Materialverfügbarkeit sowie der Witterung.",
        styles["Body"]
    ))

# ---------- MAIN GENERATOR ----------

def generate_complete_offer_pdf(run_id: str, output_path: Path | None = None) -> Path:
    print(f"🚀 [PDF] START: {run_id}")
    
    output_root = RUNNER_ROOT / "output" / run_id
    if not output_root.exists():
        raise FileNotFoundError(f"Output nu există: {output_root}")

    if output_path is None:
        pdf_dir = output_root / "offer_pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        output_path = pdf_dir / f"oferta_{run_id}.pdf"

    # Date client
    frontend_path = RUNNER_ROOT / "frontend_data.json"
    if not frontend_path.exists():
        frontend_path = RUNNER_ROOT / "fallback_frontend_data.json"
    
    frontend_data = {}
    if frontend_path.exists():
        try:
            with open(frontend_path, "r", encoding="utf-8") as f:
                frontend_data = json.load(f)
        except: pass
    client_data = frontend_data.get("client", frontend_data)

    # Load Plans
    try:
        plan_infos = load_plan_infos(run_id, stage_name="pricing")
    except PlansListError:
        plan_infos = []

    # Clasificare
    enriched_plans = []
    for plan in plan_infos:
        meta_path = output_root / "plan_metadata" / f"{plan.plan_id}.json"
        floor_type = "unknown"
        if meta_path.exists():
            try:
                with open(meta_path) as f: floor_type = json.load(f).get("floor_classification", {}).get("floor_type", "unknown")
            except: pass
        
        if floor_type == "unknown":
            if "parter" in plan.plan_id.lower() or "ground" in plan.plan_id.lower(): floor_type = "ground_floor"
            elif "etaj" in plan.plan_id.lower() or "top" in plan.plan_id.lower(): floor_type = "top_floor"

        enriched_plans.append({
            "plan": plan,
            "floor_type": floor_type,
            "sort": 0 if floor_type == "ground_floor" else 1 if floor_type == "intermediate" else 2
        })
    enriched_plans.sort(key=lambda x: x["sort"])

    # PREPROCESARE
    plans_data = []
    global_openings = []
    global_utilities = []
    
    # Colectare costuri brute
    raw_total_construction = 0.0

    for p_data in enriched_plans:
        plan = p_data["plan"]
        pricing_path = plan.stage_work_dir / "pricing_raw.json"
        if pricing_path.exists():
            with open(pricing_path, encoding="utf-8") as f:
                p_json = json.load(f)
            
            breakdown = p_json.get("breakdown", {})
            
            # 1. Utilități -> Global
            utils = breakdown.get("utilities", {}).get("items", [])
            global_utilities.extend(utils)
            
            # 2. Openings -> Global
            ops = breakdown.get("openings", {}).get("items", [])
            global_openings.extend(ops)
            
            # 3. MUTARE PEREȚI ACOPERIȘ
            roof_items = breakdown.get("roof", {}).get("items", [])
            extra_wall_item = next((it for it in roof_items if "extra_walls" in it.get("category", "")), None)
            
            if extra_wall_item:
                cost_extra = extra_wall_item.get("cost", 0.0)
                walls_struct = breakdown.get("structure_walls", {})
                walls_items = walls_struct.get("items", [])
                ext_wall_target = next((it for it in walls_items if "Außenwände" in it.get("name", "") or "Exterior" in it.get("name", "")), None)
                
                if ext_wall_target:
                    ext_wall_target["cost"] += cost_extra
                    walls_struct["total_cost"] += cost_extra
                    breakdown.get("roof", {})["total_cost"] -= cost_extra

            plans_data.append({"info": plan, "type": p_data["floor_type"], "pricing": p_json})
            
            # Calculăm totalul de construcție (fără markup-uri)
            raw_total_construction += p_json.get("total_cost_eur", 0.0)

    # --- BUILD PDF ---
    offer_no = f"CHH-{datetime.now().strftime('%Y')}-{random.randint(1000,9999)}"
    handler = "Florian Siemer"
    
    doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                            leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=42*mm, bottomMargin=22*mm,
                            title=f"Angebot {offer_no}", author=COMPANY["name"])
    
    styles = _styles()
    story = []
    
    _header_block(story, styles, offer_no, client_data)
    _intro(story, styles, client_data)

    # LOOP PLANURI
    for entry in plans_data:
        plan = entry["info"]
        pricing = entry["pricing"]
        
        story.append(PageBreak())
        
        # Imagine Plan
        if plan.plan_image.exists():
            try:
                im = PILImage.open(plan.plan_image).convert("L")
                im = ImageEnhance.Brightness(im).enhance(0.9)
                im = ImageOps.autocontrast(im)
                
                width, height = im.size
                aspect = width / height
                target_width = A4[0]-36*mm
                if aspect < 1: # Portret
                    target_width = (A4[0]-36*mm) * 0.65
                
                img_byte_arr = io.BytesIO()
                im.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                
                rl_img = Image(img_byte_arr)
                rl_img._restrictSize(target_width, 75*mm)
                rl_img.hAlign = 'CENTER'
                
                story.append(Spacer(1, 5*mm)) 
                story.append(rl_img)
                story.append(Spacer(1, 8*mm))
            except Exception as e:
                print(f"⚠️ Eroare imagine: {e}")

        # Tabele
        breakdown = pricing.get("breakdown", {})
        _table_standard(story, styles, "Tragstruktur – Wände", breakdown.get("structure_walls", {}))
        _table_standard(story, styles, "Geschossdecken", breakdown.get("floors_ceilings", {}))
        _table_roof_quantities(story, styles, pricing)
        _table_standard(story, styles, "Oberflächen & Finishes", breakdown.get("finishes", {}))

    # --- CENTRALIZATOARE ---
    _table_global_openings(story, styles, global_openings)
    _table_global_utilities(story, styles, global_utilities)

    # --- CALCUL FINAL & ASCUNDERE PROFIT ---
    story.append(PageBreak())
    story.append(Paragraph("Gesamtkostenzusammenfassung", styles["H1"]))
    
    org_percentage = 0.05
    sup_percentage = 0.05
    profit_percentage = 0.10
    
    real_org_cost = raw_total_construction * org_percentage
    real_sup_cost = raw_total_construction * sup_percentage
    real_profit_cost = raw_total_construction * profit_percentage
    
    split_profit = real_profit_cost / 2
    
    display_org_cost = real_org_cost + split_profit
    display_sup_cost = real_sup_cost + split_profit
    
    total_net = raw_total_construction + display_org_cost + display_sup_cost
    vat = total_net * 0.19
    total_gross = total_net + vat
    
    head = [P("Position", "CellBold"), P("Wert", "CellBold")]
    data = [
        [P("Baukosten (Konstruktion, Ausbau, Technik)"), P(_money(raw_total_construction))],
        [P("Baustelleneinrichtung & Logistik (10%)"), P(_money(display_org_cost))],
        [P("Bauleitung & Koordination (10%)"), P(_money(display_sup_cost))],
        [P("<b>Nettosumme</b>"), P(_money(total_net), "CellBold")],
        [P("MwSt. (19%)"), P(_money(vat))],
        [P("<b>GESAMTSUMME BRUTTO</b>"), P(_money(total_gross), "H2")],
    ]
    
    # FIX: Wrap head in a list to create the first row correctly
    tbl = Table([head] + data, colWidths=[120*mm, 50*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(tbl)
    
    _closing_blocks(story, styles)
    
    doc.build(story, onFirstPage=_first_page_canvas(offer_no, handler), onLaterPages=_later_pages_canvas)
    print(f"✅ [PDF] Generat Final: {output_path}")
    return output_path