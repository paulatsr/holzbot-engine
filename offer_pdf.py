# engine/offer_pdf.py
# -*- coding: utf-8 -*-
import os, json, logging, sys, random, time, copy
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen.canvas import Canvas

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
log = logging.getLogger("offer_pdf")

# ---------- PATHS ----------
PROJECT_ROOT = Path(__file__).resolve().parent
UI_OUT_ROOT  = PROJECT_ROOT / "ui_out"

# ---------- FONTS ----------
FONTS_DIR  = PROJECT_ROOT / "pdf_assets" / "fonts"
FONT_REG   = FONTS_DIR / "DejaVuSans.ttf"
FONT_BOLD  = FONTS_DIR / "DejaVuSans-Bold.ttf"
BASE_FONT, BOLD_FONT = "DejaVuSans", "DejaVuSans-Bold"
try:
    pdfmetrics.registerFont(TTFont(BASE_FONT, str(FONT_REG)))
    pdfmetrics.registerFont(TTFont(BOLD_FONT, str(FONT_BOLD)))
except Exception as e:
    logging.warning(f"[FONTS] DejaVuSans nicht geladen ({e}); verwende Helvetica.")
    BASE_FONT, BOLD_FONT = "Helvetica", "Helvetica-Bold"

# ---------- COMPANY ----------
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

# ---------- HELPERS ----------
def _detect_run_dir() -> Path:
    # preferă RUN_ID/UI_RUN_DIR dacă există, altfel ultimul run_*
    rid = os.getenv("UI_RUN_DIR") or os.getenv("RUN_ID")
    if rid:
        d = UI_OUT_ROOT / rid
        d.mkdir(parents=True, exist_ok=True)
        return d
    if UI_OUT_ROOT.exists():
        runs = sorted(UI_OUT_ROOT.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if runs:
            return runs[0]
    d = UI_OUT_ROOT / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _read_json_first(*cands: Path):
    for p in cands:
        if p and p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning(f"[JSON] invalid {p}: {e}")
    return {}

def _fetch_export_from_api():
    api = (os.getenv("API_URL") or "").rstrip("/")
    offer_id = os.getenv("OFFER_ID") or ""
    secret = os.getenv("ENGINE_SECRET") or ""
    if not api or not offer_id or not secret:
        return {}
    try:
        import requests
        r = requests.get(
            f"{api}/offers/{offer_id}/export",
            headers={"Content-Type":"application/json","x-engine-secret":secret},
            timeout=60
        )
        r.raise_for_status()
        return r.json() or {}
    except Exception as e:
        log.warning(f"[EXPORT] cannot fetch export: {e}")
        return {}

def _load_pipeline_data():
    run_dir = _detect_run_dir()
    rid = (os.getenv("RUN_ID") or "").strip()

    def r_ui(*parts):  # ui_out/run_<id>/...
        return run_dir.joinpath(*parts)

    def r_runs(*parts):  # runs/<RUN_ID>/...
        if not rid:
            return None
        return PROJECT_ROOT / "runs" / rid / Path(*parts)

    data = {
        "price_summary": _read_json_first(PROJECT_ROOT/"area/price_summary_full.json", r_ui("area","price_summary_full.json"), r_runs("area","price_summary_full.json")),
        "roof_price":    _read_json_first(PROJECT_ROOT/"roof/roof_price_estimation.json", r_ui("roof","roof_price_estimation.json"), r_runs("roof","roof_price_estimation.json")),
        "house_area":    _read_json_first(PROJECT_ROOT/"area/house_area_gemini.json", r_ui("area","house_area_gemini.json"), r_runs("area","house_area_gemini.json")),
        "openings_all":  _read_json_first(PROJECT_ROOT/"perimeter/openings_all.json", r_ui("perimeter","openings_all.json"), r_runs("perimeter","openings_all.json")),
        "merged_form":   _read_json_first(PROJECT_ROOT/"merged_form.json", r_ui("merged_form.json"), r_runs("merged_form.json")),
        "export_local":  _read_json_first(r_runs("export.json")),
        "client":        _read_json_first(PROJECT_ROOT/"client.json", r_ui("client","client.json"), r_runs("client","client.json")),
        "export_api":    _fetch_export_from_api(),
    }
    return run_dir, data

def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="H1", fontName=BOLD_FONT,  fontSize=12,   leading=22, spaceAfter=6))
    s.add(ParagraphStyle(name="H2", fontName=BOLD_FONT,  fontSize=12.5, leading=17, spaceBefore=10, spaceAfter=6))
    s.add(ParagraphStyle(name="Body", fontName=BASE_FONT, fontSize=10,  leading=14, spaceAfter=4))
    s.add(ParagraphStyle(name="Sub",  fontName=BASE_FONT, fontSize=9,   leading=12, textColor=colors.grey, spaceAfter=6))
    s.add(ParagraphStyle(name="Small", fontName=BASE_FONT, fontSize=7.2, leading=9.2))
    s.add(ParagraphStyle(name="Disclaimer", fontName=BASE_FONT, fontSize=8.5, leading=11, textColor=colors.HexColor("#333333")))
    s.add(ParagraphStyle(name="Cell", fontName=BASE_FONT, fontSize=9.5, leading=12))
    s.add(ParagraphStyle(name="CellBold", fontName=BOLD_FONT, fontSize=9.5, leading=12))
    s.add(ParagraphStyle(name="CellSmall", fontName=BASE_FONT, fontSize=9, leading=11))
    return s

def P(text, style_name="Cell"):
    return Paragraph((text or "").replace("\n","<br/>"), _styles()[style_name])

def _money(x):
    try:
        v = float(x)
        return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " €"
    except Exception:
        return "—"

def _get(d, *keys, default=None):
    cur = d or {}
    for k in keys:
        if not isinstance(cur, dict): 
            return default
        cur = cur.get(k)
        if cur is None: 
            return default
    return cur

def _fmt_m2(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        return "—"
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " m²"

# ---------- UI DATA EXTRACTORS ----------
def _extract_client_and_project(data: dict):
    """
    Suportă trei forme:
      A) FLAT (exact ca în exemplele tale):
         { referinta, nume, telefon, email, localitate, ... }
      B) Grupat în export_local.data sau export_api.data (tot FLAT)
      C) Grupat pe secțiuni: client.{...}, dateGenerale.{referinta}
    Returnează și 'src' pentru log.
    """
    def pick_from_flat(block: dict | None) -> tuple[dict, str] | tuple[None, str]:
        if isinstance(block, dict) and any(k in block for k in ("nume","telefon","email","localitate","referinta")):
            return block, "flat"
        return None, ""

    def pick_from_grouped(block: dict | None) -> tuple[dict, str] | tuple[None, str]:
        if not isinstance(block, dict):
            return None, ""
        # client.{...}
        c = block.get("client")
        if isinstance(c, dict) and any(k in c for k in ("nume","telefon","email","localitate")):
            out = dict(c)
            # ia și referința de lângă, dacă există
            dg = block.get("dateGenerale") or {}
            if isinstance(dg, dict) and "referinta" in dg:
                out.setdefault("referinta", dg.get("referinta"))
            return out, "grouped(client/dateGenerale)"
        return None, ""

    # 1) merged_form — întâi FLAT, apoi GROUPED
    mf = data.get("merged_form") or {}
    src = "n/a"
    client_obj, src = pick_from_flat(mf)
    if client_obj is None:
        client_obj, src = pick_from_grouped(mf)

    # 2) export_local.data — FLAT, apoi GROUPED
    if client_obj is None:
        el = (data.get("export_local") or {}).get("data") or {}
        client_obj, src = pick_from_flat(el)
        if client_obj is not None: src = f"export_local.{src}"
        if client_obj is None:
            client_obj, src = pick_from_grouped(el)
            if client_obj is not None: src = f"export_local.{src}"

    # 3) export_api.data — fallback
    if client_obj is None:
        ea = (data.get("export_api") or {}).get("data") or {}
        client_obj, src = pick_from_flat(ea)
        if client_obj is not None: src = f"export_api.{src}"
        if client_obj is None:
            client_obj, src = pick_from_grouped(ea)
            if client_obj is not None: src = f"export_api.{src}"

    # 4) client.json — ultimul fallback
    if client_obj is None:
        cj = data.get("client") or {}
        client_obj = cj if isinstance(cj, dict) else {}
        src = "client.json"

    name  = (client_obj.get("nume") or client_obj.get("name") or "").strip()
    phone = (client_obj.get("telefon") or client_obj.get("phone") or "").strip()
    email = (client_obj.get("email") or "").strip()
    city  = (client_obj.get("localitate") or client_obj.get("adresa") or client_obj.get("city") or "").strip()
    referinta = (client_obj.get("referinta") or "").strip()

    if not referinta:
        # încearcă s-o iei separat dacă e grupat/lipsă
        for container in (mf, (data.get("export_local") or {}).get("data") or {}, (data.get("export_api") or {}).get("data") or {}):
            if isinstance(container, dict):
                dg = container.get("dateGenerale")
                if isinstance(dg, dict) and isinstance(dg.get("referinta"), str) and dg["referinta"].strip():
                    referinta = dg["referinta"].strip()
                    break
                if isinstance(container.get("referinta"), str) and container["referinta"].strip():
                    referinta = container["referinta"].strip()
                    break

    if not name:
        name = "Kund/in"

    address_lines = [l for l in (city, phone, email) if l]

    # log clar + sursa
    log.info(f"[CLIENT] src={src} | name={name!r} | phone={phone!r} | email={email!r} | city={city!r} | referinta={referinta!r}")

    return {
        "name": name,
        "phone": phone,
        "email": email,
        "city": city,
        "address_lines": address_lines,
        "handler": "Florian Siemer",
        "project_label": referinta or "Projekt",
    }

def _greeting_line(client: dict) -> str:
    name = (client.get("name") or "").strip()
    if name:
        return f"Sehr geehrte Kundschaft,"
    return "Sehr geehrte Kundschaft,"


# ---------- CANVAS DECOR ----------
def _draw_ribbon(canv: Canvas):
    canv.saveState()
    x, y = 18*mm, A4[1]-23*mm
    w, h = A4[0]-36*mm, 9*mm
    canv.setFillColor(colors.HexColor("#1c1c1c"))
    canv.rect(x, y, w, h, stroke=0, fill=1)
    canv.setFillColor(colors.white)
    canv.setFont(BOLD_FONT, 10)
    canv.drawString(x+6*mm, y+2.35*mm,
        "ANGEBOT – UNVERBINDLICHE KOSTENSCHÄTZUNG (RICHTWERT) ±10 %")
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
    for i,(k,v) in enumerate(rows):
        y = box_y - (i+1)*row_h + 2.6*mm
        canv.drawString(box_x+3*mm, y, k)
        canv.drawRightString(box_x+cw-3*mm, y, v)
    canv.restoreState()

def _draw_footer(canv: Canvas):
    canv.saveState()
    y = 9*mm
    colw = (A4[0]-36*mm)/3.0
    x0 = 18*mm
    canv.setFont(BASE_FONT, 6.6)
    for i,block in enumerate((COMPANY["footer_left"], COMPANY["footer_mid"], COMPANY["footer_right"])):
        tx = x0 + i*colw
        for idx, line in enumerate(block.split("\n")):
            canv.drawString(tx, y + (idx*3.0*mm), line)
    canv.restoreState()

def _first_page_canvas(offer_no: str, handler: str):
    def _inner(canv: Canvas, doc):
        _draw_ribbon(canv)
        logos = PROJECT_ROOT / "offer_logos.png"
        ident = PROJECT_ROOT / "offer_identity.png"
        if ident.exists():
            canv.drawImage(str(ident), A4[0]-18*mm-85*mm, A4[1]-53*mm, 85*mm, 22*mm, preserveAspectRatio=True, mask='auto')
        if logos.exists():
            canv.drawImage(str(logos), 18*mm, A4[1]-55*mm, 80*mm, 26*mm, preserveAspectRatio=True, mask='auto')
        _draw_firstpage_right_box(canv, offer_no, handler)
        _draw_footer(canv)
    return _inner

def _noop(canv, doc):
    pass

# ---------- TABLE HELPERS ----------
def _openings_agg_from_ps(ps: dict):
    items = (((ps or {}).get("components") or {}).get("openings") or {}).get("items", []) or []
    def is_win(t): return t in ("window","double_window")
    def is_door(t): return t in ("door","double-door","double_door")
    agg = {"doors_int": {"n":0,"eur":0.0}, "doors_ext":{"n":0,"eur":0.0}, "windows":{"n":0,"eur":0.0}}
    for it in items:
        t = str(it.get("type","")).lower().replace("-", "_")
        st= str(it.get("status","")).lower()
        val= float((it.get("calculation") or {}).get("result_eur", 0.0) or 0.0)
        if is_win(t):
            agg["windows"]["n"]  += 1; agg["windows"]["eur"]+= val
        elif is_door(t):
            if st in ("exterior","outside","outer"):
                agg["doors_ext"]["n"]+=1; agg["doors_ext"]["eur"]+=val
            else:
                agg["doors_int"]["n"]+=1; agg["doors_int"]["eur"]+=val
    return agg

# ---------- CONTENT ----------
def _header_block(story, styles, offer_no: str, client: dict):
    # stânga: date companie (rămân în tabelul din header)
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

    # dreapta: gol (nu mai punem datele clientului aici)
    right_par = Paragraph("", styles["Small"])

    data = [[left_par, right_par]]
    tbl = Table(data, colWidths=[95*mm, A4[0]-36*mm-95*mm])
    tbl.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
    ]))

    story.append(Spacer(1, 34*mm))
    story.append(tbl)
    story.append(Spacer(1, 6*mm))

    # Titlul de ofertă
    story.append(Paragraph(f"Angebot • Nr.: {offer_no}", styles["H1"]))
    story.append(Spacer(1, 3*mm))

    story.append(_client_info_block(client))
    story.append(Spacer(1, 6*mm))

def _client_info_block(client: dict):
    name   = (client.get("name") or "—").strip()
    city   = (client.get("city") or "—").strip()
    phone  = (client.get("phone") or "—").strip()
    email  = (client.get("email") or "—").strip()
    proj   = (client.get("project_label") or "—").strip()

    lines = [
        f"<b>Kundin/Kunde:</b> {name}",
        f"<b>Ort:</b> {city}",
        f"<b>Telefon:</b> {phone}",
        f"<b>E-Mail:</b> {email}",
        f"<b>Projekt:</b> {proj}",
    ]
    return Paragraph("<br/>".join(lines), _styles()["Cell"])

def _client_sentence(client: dict) -> str:
    parts = []
    # păstrat pentru compatibilitate; momentan nu e folosit
    return " – ".join(parts)

def _client_info_table(client: dict, styles):
    rows = []
    def add(label, value):
        v = (value or "").strip()
        rows.append([P(label, "CellBold"), P(v if v else "—", "Cell")])

    add("Kundin/Kunde", client.get("name"))
    add("Ort",          client.get("city"))
    add("Telefon",      client.get("phone"))
    add("E-Mail",       client.get("email"))
    add("Projekt",      client.get("project_label"))

    tbl = Table(rows, colWidths=[32*mm, A4[0] - 36*mm - 32*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f7f7f7")),
        ("ALIGN", (0,0), (0,-1), "LEFT"),
    ]))
    return tbl

def _intro(story, styles, client):
    story.append(Paragraph("Angebot für Ihr Chiemgauer Massivholzhaus als Komplettmontage", styles["H2"]))
    story.append(Paragraph(_greeting_line(client), styles["Body"]))

    for p in [
        "vielen Dank für Ihre Anfrage. Gerne haben wir für Sie das nachstehende Angebot ausgearbeitet.",
        "Bitte setzen Sie sich bei Rückfragen jederzeit mit uns in Verbindung, um das Angebot detaillierter zu besprechen.",
    ]:
        story.append(Paragraph(p, styles["Body"]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "Hinweis/Haftungsausschluss: Dieses Dokument stellt eine unverbindliche, orientierende Kostenschätzung dar und ist kein offizielles Angebot im rechtlichen Sinne. "
        "Die aufgeführten Werte können sich je nach Ausführungsplanung, tatsächlichen Baustellenbedingungen und finalen Entscheidungen ändern.",
        styles["Disclaimer"]
    ))
    story.append(Spacer(1, 6*mm))

def _plan_after_intro(story):
    from PIL import Image as PILImage, ImageEnhance, ImageOps
    plan = PROJECT_ROOT / "plan.jpg"
    if not plan.exists():
        log.info("[PLAN] plan.jpg fehlt – überspringe.")
        return
    run_dir = _detect_run_dir()
    out_dir = run_dir / "oferta"
    out_dir.mkdir(parents=True, exist_ok=True)
    gray = out_dir / "plan_gray.png"
    try:
        im = PILImage.open(plan).convert("L")
        im = ImageEnhance.Brightness(im).enhance(0.9)
        im = ImageOps.autocontrast(im)
        im.save(gray)
        img = Image(str(gray))
        img._restrictSize(A4[0]-36*mm, 75*mm)
        story.append(img)
        story.append(Spacer(1, 8*mm))
    except Exception as e:
        log.warning(f"[PLAN] Bildverarbeitung fehlgeschlagen: {e}")

def _table_structures(story, styles, ps, Hm2, areas_override: dict | None = None):
    """
    Dacă areas_override este dat, îl folosim ca suprafețe afișate:
      - areas_override['int']  -> Fläche interior walls (brut, inclusiv geamuri/usi)
      - areas_override['ext']  -> Fläche exterior walls (brut)
      - areas_override['house']-> Fläche totală casă pentru rândurile de Boden/Decke
    Costurile rămân cele din ps (împărțite la nevoie pe planuri).
    """
    story.append(Paragraph("Konstruktionen & Oberflächen", styles["H2"]))
    comps = ps.get("components", {}) if isinstance(ps, dict) else {}
    # valori din price_summary (net)
    a_int_net = float(_get(comps,"walls_structure","calculations","interior","values","net_area_m2", default=0.0) or 0.0)
    a_ext_net = float(_get(comps,"walls_structure","calculations","exterior","values","net_area_m2", default=0.0) or 0.0)
    fin_int_unit = float(_get(comps,"wall_finishes","calculations","interior","values","finish_unit_int_eur_per_m2", default=0.0) or 0.0)
    fin_ext_unit = float(_get(comps,"wall_finishes","calculations","exterior","values","finish_unit_ext_eur_per_m2", default=0.0) or 0.0)
    fin_int_total = float(_get(comps,"wall_finishes","calculations","interior","result_eur", default=a_int_net*fin_int_unit) or 0.0)
    fin_ext_total = float(_get(comps,"wall_finishes","calculations","exterior","result_eur", default=a_ext_net*fin_ext_unit) or 0.0)
    unit_int = float(_get(ps,"system_and_prefab","unit_prices_applied","interior_eur_per_m2", default=0.0) or 0.0)
    unit_ext = float(_get(ps,"system_and_prefab","unit_prices_applied","exterior_eur_per_m2", default=0.0) or 0.0)
    int_total = float(_get(comps,"walls_structure","calculations","interior","result_eur", default=a_int_net*unit_int) or 0.0)
    ext_total = float(_get(comps,"walls_structure","calculations","exterior","result_eur", default=a_ext_net*unit_ext) or 0.0)
    floor_total   = float(_get(comps,"floor_system","calculations","total_floor_eur", default=0.0) or 0.0)
    ceiling_total = float(_get(comps,"ceiling_system","calculations","result_eur", default=0.0) or 0.0)

    # suprafețe afișate = override (brut) dacă există, altfel net
    a_int_disp = float(areas_override.get("int", a_int_net)) if areas_override else a_int_net
    a_ext_disp = float(areas_override.get("ext", a_ext_net)) if areas_override else a_ext_net
    Hm2_disp   = float(areas_override.get("house", Hm2)) if areas_override else Hm2

    head = [P("Element","CellBold"), P("Fläche","CellBold"), P("Preis/m²","CellBold"), P("Wert","CellBold")]
    data = [
        [P("Baustellengrundlage / Bodenplatte & Decken","CellBold"),
         P(_fmt_m2(Hm2_disp) if Hm2_disp else "—"),
         P(_money((floor_total/Hm2_disp) if Hm2_disp else 0.0),"CellSmall"),
         P(_money(floor_total))],
        [P("Innenwände – Tragstruktur","CellBold"),
         P(_fmt_m2(a_int_disp)),
         P(_money(unit_int),"CellSmall"),
         P(_money(int_total))],
        [P("Außenwände – Tragstruktur","CellBold"),
         P(_fmt_m2(a_ext_disp)),
         P(_money(unit_ext),"CellSmall"),
         P(_money(ext_total))],
        [P("Innenwand-Oberflächen","CellBold"),
         P(_fmt_m2(a_int_disp)),
         P(_money(fin_int_unit),"CellSmall"),
         P(_money(fin_int_total))],
        [P("Außenwand-Oberflächen","CellBold"),
         P(_fmt_m2(a_ext_disp)),
         P(_money(fin_ext_unit),"CellSmall"),
         P(_money(fin_ext_total))],
        [P("Fußboden + Decke (gesamt)","CellBold"),
         P(_fmt_m2(Hm2_disp) if Hm2_disp else "—"),
         P(_money((ceiling_total/Hm2_disp) if Hm2_disp else 0.0),"CellSmall"),
         P(_money(ceiling_total))],
    ]
    tbl = Table([head] + data, colWidths=[75*mm, 40*mm, 32*mm, 38*mm])
    tbl.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.3,colors.black),
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#f2f2f2")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("ALIGN",(1,1),(-1,-1),"RIGHT"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

def _table_roof(story, styles, roof):
    story.append(Paragraph("Dach – Detail", styles["H2"]))
    inputs = roof.get("inputs", {}) if isinstance(roof, dict) else {}
    comps  = roof.get("components", {}) if isinstance(roof, dict) else {}
    area   = float(_get(inputs,"house_area_m2", default=0.0) or 0.0)
    base   = float(_get(comps,"roof_base","average_total_eur", default=0.0) or 0.0)
    extra  = float(_get(comps,"extra_walls","total_eur", default=0.0) or 0.0)
    tin    = float(_get(comps,"sheet_metal","total_eur", default=0.0) or 0.0)
    tin_ml = float(_get(comps,"sheet_metal","total_length_m", default=0.0) or 0.0)
    ins    = float(_get(comps,"insulation","total_eur", default=0.0) or 0.0)

    def qty(q, u): return f"{q:.2f} {u}" if q else "—"

    head = [P("Komponente","CellBold"), P("Bemerkungen","CellBold"), P("Einheit","CellBold"), P("Preis","CellBold")]
    data = [
        [P("Dachstruktur","Cell"), P("Sparren, Schalung; integrierte Zusatzwände","CellSmall"), P(qty(area,"m²"),"CellSmall"), P(_money(base+extra))],
        [P("Spenglerarbeiten","Cell"), P("Abschlüsse, Bleche, Rinnen/Fallrohre","CellSmall"), P(qty(tin_ml,"lfm"),"CellSmall"), P(_money(tin))],
        [P("Dämmung","Cell"), P("Thermo-/Akustikaufbau gem. Planung","CellSmall"), P(qty(area,"m²"),"CellSmall"), P(_money(ins))],
    ]
    tbl = Table([head] + data, colWidths=[55*mm, 70*mm, 24*mm, 32*mm])
    tbl.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.3,colors.black),
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#f2f2f2")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("ALIGN",(2,1),(3,-1),"RIGHT"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

def _table_openings(story, styles, ps):
    story.append(Paragraph("Öffnungen (Türen / Fenster)", styles["H2"]))
    agg = _openings_agg_from_ps(ps)
    def avg(total, n):
        return (total / n) if (n and total) else 0.0
    head = ["Kategorie", "Stück", "Preis/Stk.", "Gesamt"]
    data = [
        ["Innentüren",  agg["doors_int"]["n"], _money(avg(agg["doors_int"]["eur"], agg["doors_int"]["n"])), _money(agg["doors_int"]["eur"])],
        ["Außentüren",  agg["doors_ext"]["n"], _money(avg(agg["doors_ext"]["eur"], agg["doors_ext"]["n"])), _money(agg["doors_ext"]["eur"])],
        ["Fenster",     agg["windows"]["n"],   _money(avg(agg["windows"]["eur"],   agg["windows"]["n"])),   _money(agg["windows"]["eur"])],
    ]
    tbl = Table([head] + data, colWidths=[68*mm, 26*mm, 34*mm, 40*mm])
    tbl.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.3,colors.black),
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#f2f2f2")),
        ("ALIGN",(1,1),(-1,-1),"RIGHT"),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("FONTNAME",(0,0),(-1,0),BOLD_FONT),
        ("FONTNAME",(0,1),(-1,-1),BASE_FONT),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

def _table_installations(story, styles, ps):
    story.append(Paragraph("Haustechnik", styles["H2"]))
    comps = ps.get("components", {})
    el = float(_get(comps,"services","totals","electricity_eur", default=0.0) or 0.0)
    sw = float(_get(comps,"services","totals","sewage_eur", default=0.0) or 0.0)
    ht = float(_get(comps,"services","totals","heating_eur", default=0.0) or 0.0)
    head = [P("Kategorie","CellBold"), P("Wert","CellBold")]
    data = [
        [P("Elektro"), P(_money(el))],
        [P("Abwasser/Entwässerung"), P(_money(sw))],
        [P("Heizung"), P(_money(ht))],
    ]
    tbl = Table([head] + data, colWidths=[90*mm, 80*mm])
    tbl.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.3,colors.black),
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#f2f2f2")),
        ("ALIGN",(1,1),(1,-1),"RIGHT"),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

def _table_totals(story, styles, ps):
    story.append(Paragraph("Kostenzusammenfassung & Zwischensummen", styles["H2"]))
    oc = ps.get("offer_calculations", {}) if isinstance(ps, dict) else {}
    subtotal = float(_get(oc,"pre_context_house_value_eur", default=0.0) or 0.0)
    org_eur  = float(_get(oc,"organization_component","result_eur", default=0.0) or 0.0)
    sup_eur  = float(_get(oc,"supervising_component","result_eur", default=0.0) or 0.0)
    vat_rate = float(_get(ps,"summary","offer","coefficients","vat", default=0.19) or 0.19)
    semi     = float(_get(oc,"semi_value","result_eur", default=subtotal + org_eur + sup_eur) or 0.0)
    final_offer = float(_get(oc,"final_offer","result_eur", default=semi*(1+vat_rate)) or semi*(1+vat_rate))
    vat_eur  = max(final_offer - semi, 0.0)

    head = [P("Position","CellBold"), P("Wert","CellBold")]
    data = [
        [P("Zwischensumme (Konstruktionen, Oberflächen, Haustechnik)"), P(_money(subtotal))],
        [P("Baustelleneinrichtung/Organisation"), P(_money(org_eur))],
        [P("Bauüberwachung"), P(_money(sup_eur))],
        [P(f"Umsatzsteuer (MwSt., {int(vat_rate*100)} %)"), P(_money(vat_eur))],
    ]
    tbl = Table([head] + data, colWidths=[112*mm, 58*mm])
    tbl.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.3,colors.black),
        ("ALIGN",(1,1),(1,-1),"RIGHT"),
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#f2f2f2")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(f"Gesamtsumme inkl. MwSt.: <b>{_money(final_offer)}</b>", _styles()["H2"]))
    story.append(Spacer(1, 8*mm))

def _closing_blocks(story, styles):
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
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("Nächste Schritte", styles["H2"]))
    story.append(Paragraph(
        "Nach Einigung über die Schätzung werden die technischen Details finalisiert und der Produktions-/Montageplan abgestimmt. "
        "Rückfragen klären wir gerne in einem technischen Gespräch vor Beauftragung.",
        styles["Body"]
    ))

# ---------- HELPERI MULTI-PLAN ----------
def _scale_in_dict(d: dict, path: tuple[str, ...], ratio: float):
    """
    Scalează o valoare numerică din dict pe path dat, in-place.
    """
    cur = d
    for k in path[:-1]:
        if not isinstance(cur, dict):
            return
        cur = cur.get(k)
        if cur is None:
            return
    last = path[-1]
    try:
        if isinstance(cur, dict) and last in cur and isinstance(cur[last], (int, float)):
            cur[last] = float(cur[last]) * ratio
    except Exception:
        return

def _plan_wall_gross_areas(plan: dict) -> tuple[float,float]:
    wa = (plan.get("wall_areas") or {}).get("computed_areas") or {}
    a_int = float(wa.get("interior_walls_area_m2", 0.0) or 0.0)
    a_ext = float(wa.get("exterior_walls_area_m2", 0.0) or 0.0)
    return a_int, a_ext

def _plan_house_area(plan: dict) -> float:
    return float(
        _get(plan, "house_area", "surface_estimation", "final_area_m2", default=0.0) or 0.0
    )

def _plan_id(plan: dict, idx: int) -> str:
    if isinstance(plan.get("planId"), str) and plan["planId"].strip():
        return plan["planId"].strip()
    i = plan.get("planIndex") or idx
    try:
        i = int(i)
    except Exception:
        i = idx
    return f"p{i:02d}"

def _plan_image_for_id(story, plan_id: str):
    """
    Caută poză pentru plan:
      - plan_<plan_id>.jpg / .png
      - fallback: plan.jpg
    O convertește în grayscale similar cu _plan_after_intro.
    """
    from PIL import Image as PILImage, ImageEnhance, ImageOps
    candidates = [
        PROJECT_ROOT / f"plan_{plan_id}.jpg",
        PROJECT_ROOT / f"plan_{plan_id}.png",
        PROJECT_ROOT / "plan.jpg",
    ]
    plan_path = None
    for c in candidates:
        if c.exists():
            plan_path = c
            break
    if not plan_path:
        log.info(f"[PLAN] niciun plan_* pentru {plan_id} – sar peste imagine.")
        return

    run_dir = _detect_run_dir()
    out_dir = run_dir / "oferta"
    out_dir.mkdir(parents=True, exist_ok=True)
    gray = out_dir / f"plan_{plan_id}_gray.png"
    try:
        im = PILImage.open(plan_path).convert("L")
        im = ImageEnhance.Brightness(im).enhance(0.9)
        im = ImageOps.autocontrast(im)
        im.save(gray)
        img = Image(str(gray))
        img._restrictSize(A4[0]-36*mm, 75*mm)
        story.append(img)
        story.append(Spacer(1, 8*mm))
    except Exception as e:
        log.warning(f"[PLAN] Bildverarbeitung {plan_id} fehlgeschlagen: {e}")

def _build_plan_ps_from_total(total_ps: dict, plan: dict, ratio: float) -> dict:
    """
    Construiește un pseudo-price_summary pentru un singur plan:
      - copiază total_ps
      - scalează valorile monetare și ariile relevante cu ratio = area_plan / area_total
      - planul are propria house_area_m2 în summary
      - pentru suprafețe afișate (Fläche) folosim override în _table_structures
    """
    ps = copy.deepcopy(total_ps) if isinstance(total_ps, dict) else {}
    area_plan = _plan_house_area(plan)
    ps.setdefault("summary", {})
    ps["summary"]["house_area_m2"] = area_plan

    if ratio <= 0:
        return ps

    # scale summary
    paths = [
        ("summary","final_structure_eur"),
        ("summary","final_house_eur"),
        ("summary","offer","value_semi_eur"),
        ("summary","offer","final_offer_eur"),
    ]
    for pth in paths:
        _scale_in_dict(ps, pth, ratio)

    # scale components (structuri, finisaje, podea, tavan, beci)
    comp_paths = [
        # walls_structure
        ("components","walls_structure","calculations","interior","values","net_area_m2"),
        ("components","walls_structure","calculations","interior","result_eur"),
        ("components","walls_structure","calculations","exterior","values","net_area_m2"),
        ("components","walls_structure","calculations","exterior","result_eur"),

        # wall_finishes
        ("components","wall_finishes","calculations","interior","values","net_area_int_m2"),
        ("components","wall_finishes","calculations","interior","result_eur"),
        ("components","wall_finishes","calculations","exterior","values","net_area_ext_m2"),
        ("components","wall_finishes","calculations","exterior","result_eur"),

        # floor_system
        ("components","floor_system","calculations","foundation","values","area_m2"),
        ("components","floor_system","calculations","foundation","result_eur"),
        ("components","floor_system","calculations","floors","values","area_m2"),
        ("components","floor_system","calculations","floors","result_eur"),
        ("components","floor_system","calculations","total_floor_eur",),

        # ceiling_system
        ("components","ceiling_system","calculations","values","area_m2"),
        ("components","ceiling_system","calculations","result_eur"),

        # basement_system
        ("components","basement_system","calculations","values","area_beci_m2"),
        ("components","basement_system","calculations","result_eur"),

        # services totals
        ("components","services","totals","electricity_eur"),
        ("components","services","totals","sewage_eur"),
        ("components","services","totals","heating_eur"),
        ("components","services","totals","ventilation_eur"),
        ("components","services","totals","services_sum_eur"),
    ]
    for pth in comp_paths:
        _scale_in_dict(ps, pth, ratio)

    # roof_breakdown
    roof_paths = [
        ("roof_breakdown","roof_base_avg_eur"),
        ("roof_breakdown","sheet_metal_eur"),
        ("roof_breakdown","extra_walls_eur"),
        ("roof_breakdown","insulation_eur"),
        ("roof_breakdown","roof_final_total_eur"),
    ]
    for pth in roof_paths:
        _scale_in_dict(ps, pth, ratio)

    # offer_calculations
    offer_paths = [
        ("offer_calculations","pre_context_house_value_eur"),
        ("offer_calculations","organization_component","result_eur"),
        ("offer_calculations","organization_component","values","pre_context"),
        ("offer_calculations","organization_component","values","org_ctx"),
        ("offer_calculations","supervising_component","result_eur"),
        ("offer_calculations","supervising_component","values","pre_context"),
        ("offer_calculations","profit_component","result_eur"),
        ("offer_calculations","profit_component","values","pre_context"),
        ("offer_calculations","semi_value","result_eur"),
        ("offer_calculations","semi_value","values","pre_context"),
        ("offer_calculations","semi_value","values","org_ctx"),
        ("offer_calculations","semi_value","values","supervising"),
        ("offer_calculations","semi_value","values","profit"),
        ("offer_calculations","final_offer","result_eur"),
        ("offer_calculations","final_offer","values","semi_value"),
    ]
    for pth in offer_paths:
        _scale_in_dict(ps, pth, ratio)

    # openings per plan: folosim item-ele brute din engine_plans
    plan_openings = plan.get("openings") or []
    ps.setdefault("components", {}).setdefault("openings", {})
    ps["components"]["openings"]["items"] = plan_openings

    return ps

def _build_roof_for_plan(total_roof: dict, plan: dict, ratio: float) -> dict:
    """
    Creează structura roof pentru un plan:
      - dacă plan["roof_price"] există, o folosește
      - altfel folosește total_roof scalat cu ratio
      - setează inputs.house_area_m2 = area_plan
    """
    area_plan = _plan_house_area(plan)
    if isinstance(plan.get("roof_price"), dict) and plan["roof_price"]:
        roof = copy.deepcopy(plan["roof_price"])
    else:
        roof = copy.deepcopy(total_roof) if isinstance(total_roof, dict) else {}
        # scalează sumele dacă nu avem roof per plan
        paths = [
            ("components","roof_base","average_total_eur"),
            ("components","extra_walls","total_eur"),
            ("components","sheet_metal","total_eur"),
            ("components","insulation","total_eur"),
        ]
        for pth in paths:
            _scale_in_dict(roof, pth, ratio)
    roof.setdefault("inputs", {})
    roof["inputs"]["house_area_m2"] = area_plan
    return roof

def _append_per_plan_sections(story, styles, total_ps: dict, total_roof: dict, engine_plans: list[dict]):
    """
    Appendix per plan: pentru fiecare plan:
      - pagină nouă
      - titlu + info
      - imagine plan_<planId>.jpg/png
      - aceleași tabele ca în total, dar cu valori scalate și suprafețe brute per plan
    """
    if not engine_plans:
        return

    # aria totală (fallback la sumă dacă lipsește din summary)
    total_area = float(_get(total_ps,"summary","house_area_m2", default=0.0) or 0.0)
    if total_area <= 0:
        total_area = 0.0
        for pl in engine_plans:
            total_area += _plan_house_area(pl)
    if total_area <= 0:
        return

    for idx, plan in enumerate(engine_plans, start=1):
        area_plan = _plan_house_area(plan)
        if area_plan <= 0:
            continue
        ratio = area_plan / total_area
        pid = _plan_id(plan, idx)
        walls_int_gross, walls_ext_gross = _plan_wall_gross_areas(plan)

        plan_ps = _build_plan_ps_from_total(total_ps, plan, ratio)
        plan_roof = _build_roof_for_plan(total_roof, plan, ratio)

        # pagină nouă
        story.append(PageBreak())
        story.append(Paragraph(f"Anhang – Plan {pid}", styles["H2"]))
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(
            f"Wohnfläche dieses Plans (brutto): <b>{_fmt_m2(area_plan)}</b>",
            styles["Body"]
        ))
        story.append(Spacer(1, 4*mm))

        # imagine plan
        _plan_image_for_id(story, pid)

        # tabele per plan
        _table_structures(
            story,
            styles,
            plan_ps,
            area_plan,
            areas_override={"int": walls_int_gross, "ext": walls_ext_gross, "house": area_plan}
        )
        _table_roof(story, styles, plan_roof)
        _table_openings(story, styles, plan_ps)
        _table_installations(story, styles, plan_ps)
        _table_totals(story, styles, plan_ps)

# ---------- UPLOAD TO BACKEND (presign + PUT + register) ----------
def _upload_offer_pdf_to_backend(pdf_path: str, delay_before_register_s: int = 60) -> bool:
    api      = (os.getenv("API_URL") or "").rstrip("/")
    offer_id = os.getenv("OFFER_ID") or ""
    secret   = os.getenv("ENGINE_SECRET") or ""

    if not (api and offer_id and secret and pdf_path):
        log.error("[upload_offer_pdf] Lipsesc API_URL / OFFER_ID / ENGINE_SECRET sau pdf_path.")
        return False

    p = Path(pdf_path)
    if not p.exists():
        log.error(f"[upload_offer_pdf] PDF inexistent: {p}")
        return False

    try:
        import requests
        # 1) presign
        r1 = requests.post(
            f"{api}/offers/{offer_id}/file/presign",
            json={"filename": p.name, "contentType": "application/pdf", "size": p.stat().st_size},
            headers={"Content-Type": "application/json", "x-engine-secret": secret},
            timeout=60
        )
        r1.raise_for_status()
        pres = r1.json()

        # 2) upload (PUT)
        put_headers = {"Content-Type": "application/pdf"}
        if pres.get("uploadToken"):
            put_headers["Authorization"] = f"Bearer {pres['uploadToken']}"
        with p.open("rb") as fh:
            r2 = requests.put(pres["uploadUrl"], data=fh, headers=put_headers, timeout=600)
        r2.raise_for_status()

        # ⌛ 2.5) Așteaptă înainte de „register” ca să nu apară URL-ul
        if delay_before_register_s > 0:
            log.info(f"⌛ Aștept {delay_before_register_s}s înainte de înregistrarea PDF-ului…")
            time.sleep(delay_before_register_s)

        # 3) register în DB (abia ACUM apare URL-ul în export-url)
        r3 = requests.post(
            f"{api}/offers/{offer_id}/file",
            json={
                "storagePath": pres["storagePath"],
                "meta": {"filename": p.name, "kind": "offerPdf", "mime": "application/pdf", "size": p.stat().st_size}
            },
            headers={"Content-Type": "application/json", "x-engine-secret": secret},
            timeout=60
        )
        r3.raise_for_status()
        log.info("✅ offerPdf înregistrat în backend (după delay).")
        return True
    except Exception as e:
        log.exception(f"[upload_offer_pdf] Eșec upload/register: {e}")
        return False


def _fetch_fresh_export_url() -> str | None:
    """
    Opțional: cere un URL semnat fresh pt. afișare (StepWizard oricum îl cere periodic).
    O folosim doar pentru log/diagnostic, nu e necesar pentru UI.
    """
    api      = (os.getenv("API_URL") or "").rstrip("/")
    offer_id = os.getenv("OFFER_ID") or ""
    secret   = os.getenv("ENGINE_SECRET") or ""
    if not (api and offer_id and secret):
        return None
    try:
        import requests
        r = requests.get(
            f"{api}/offers/{offer_id}/export-url",
            headers={"Content-Type":"application/json","x-engine-secret":secret},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json() or {}
            return data.get("url") or data.get("download_url") or data.get("pdf")
        return None
    except Exception:
        return None

# ---------- LIVEFEED NOTIFY (nou: atașează PDF dacă există) ----------
def _maybe_notify_livefeed_final(pdf_url: str | None = None):
    """
    Opțional: dacă ai net_bridge.post_event disponibil, marcăm în feed un mesaj 'final'.
    Dacă pdf_url este furnizat, atașăm fișierul PDF în eveniment, astfel încât LiveFeed
    să detecteze payload.files[*].pdf și să emită cardul 'congrats' + buton de download.
    """
    try:
        from net_bridge import post_event
    except Exception:
        return
    try:
        files = []
        if pdf_url:
            files = [{"url": pdf_url, "mime": "application/pdf", "caption": "oferta.pdf"}]
        post_event("[house_pricing] PDF generat", files=files)
    except Exception:
        pass

# ---------- MAIN ----------
def generate_offer_pdf():
    run_dir, data = _load_pipeline_data()
    client = _extract_client_and_project(data)
    log.info(f"[CLIENT] name={client.get('name')!r} | phone={client.get('phone')!r} | email={client.get('email')!r} | city={client.get('city')!r}")

    ps   = data.get("price_summary") or {}
    roof = data.get("roof_price") or {}
    Hm2  = float(_get(data,"house_area","surface_estimation","final_area_m2", default=0.0) or 0.0)

    offer_no = f"CHH-{datetime.now().strftime('%Y')}-{random.randint(1000,9999)}"
    handler  = client.get("handler") or "Florian Siemer"

    out_dir = run_dir / "oferta"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = out_dir / "oferta_local.pdf"

    styles = _styles()
    doc = SimpleDocTemplate(
        str(out_pdf),
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=20*mm, bottomMargin=22*mm,
        title=f"Angebot – Schätzung • {offer_no}", author=COMPANY["name"]
    )

    story = []
    _header_block(story, styles, offer_no, client)
    _intro(story, styles, client)
    _plan_after_intro(story)
    _table_structures(story, styles, ps, Hm2)        # total (vechi)
    _table_roof(story, styles, roof)
    _table_openings(story, styles, ps)
    _table_installations(story, styles, ps)
    _table_totals(story, styles, ps)
    _closing_blocks(story, styles)

    # 🔹 Appendix per plan (multi-plan)
    engine_plans = ps.get("engine_plans") or []
    _append_per_plan_sections(story, styles, ps, roof, engine_plans)

    doc.build(
        story,
        onFirstPage=_first_page_canvas(offer_no, handler),
        onLaterPages=_noop
    )

    print(f"📄 PDF generiert: {out_pdf}")
    return str(out_pdf)

pdf_path = generate_offer_pdf()

# ⚠️ facem upload + register după 60s (întârziem apariția URL-ului)
ok = _upload_offer_pdf_to_backend(pdf_path, delay_before_register_s=60)
if not ok:
    sys.exit(2)

# acum există deja înregistrarea; putem cere un export-url proaspăt
fresh = _fetch_fresh_export_url()

# trimitem evenimentele în LiveFeed (acum sincron cu apariția URL-ului)
_maybe_notify_livefeed_final(fresh)
try:
    from net_bridge import post_event
    files = [{"url": fresh, "mime": "application/pdf", "caption": "oferta.pdf"}] if fresh else []
    post_event("[house_pricing] PDF upload complet", files=files)
except Exception:
    pass
