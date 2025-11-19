# new/runner/pdf_generator/tables.py
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.units import mm

from .styles import get_styles, COLORS, BOLD_FONT, BASE_FONT
from .utils import format_money, format_area, format_length, safe_get


def P(text: str, style_name: str = "Cell") -> Paragraph:
    """Helper pentru creare Paragraph"""
    styles = get_styles()
    return Paragraph(str(text).replace("\n", "<br/>"), styles[style_name])


def create_client_info_table(client_data: dict) -> Table:
    """Tabel cu informații client"""
    rows = [
        [P("Client", "CellBold"), P(client_data.get("nume", "—"), "Cell")],
        [P("Telefon", "CellBold"), P(client_data.get("telefon", "—"), "Cell")],
        [P("Email", "CellBold"), P(client_data.get("email", "—"), "Cell")],
        [P("Localitate", "CellBold"), P(client_data.get("localitate", "—"), "Cell")],
        [P("Proiect", "CellBold"), P(client_data.get("referinta", "—"), "Cell")],
    ]
    
    table = Table(rows, colWidths=[40*mm, 130*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("BACKGROUND", (0,0), (0,-1), COLORS["bg_header"]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    
    return table


def create_plan_summary_table(plan_data: dict, plan_id: str) -> Table:
    """Tabel rezumat plan individual"""
    floor_type = safe_get(plan_data, "floor_type", default="unknown")
    house_area = safe_get(plan_data, "house_area_m2", default=0.0)
    
    floor_names = {
        "ground_floor": "Parter (Ground Floor)",
        "top_floor": "Etaj (Top Floor)",
        "intermediate": "Etaj Intermediar",
        "unknown": "Necunoscut"
    }
    
    rows = [
        [P("Plan ID", "CellBold"), P(plan_id, "Cell")],
        [P("Tip Etaj", "CellBold"), P(floor_names.get(floor_type, floor_type), "Cell")],
        [P("Suprafață Totală", "CellBold"), P(format_area(house_area), "Cell")],
    ]
    
    table = Table(rows, colWidths=[50*mm, 120*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("BACKGROUND", (0,0), (0,-1), COLORS["bg_light"]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
    ]))
    
    return table


def create_walls_table(walls_data: dict) -> Table:
    """Tabel detaliat pereți (interior + exterior)"""
    interior = walls_data.get("interior", {})
    exterior = walls_data.get("exterior", {})
    
    rows = [
        [P("Categorie", "CellBold"), P("Lungime", "CellBold"), 
         P("Arie Brută", "CellBold"), P("Arie Goluri", "CellBold"), 
         P("Arie Netă", "CellBold")]
    ]
    
    # Pereți interiori
    rows.append([
        P("Pereți Interiori", "Cell"),
        P(format_length(interior.get("length_m")), "Cell"),
        P(format_area(interior.get("gross_area_m2")), "Cell"),
        P(format_area(interior.get("openings_area_m2")), "Cell"),
        P(format_area(interior.get("net_area_m2")), "CellBold"),
    ])
    
    # Pereți exteriori
    rows.append([
        P("Pereți Exteriori", "Cell"),
        P(format_length(exterior.get("length_m")), "Cell"),
        P(format_area(exterior.get("gross_area_m2")), "Cell"),
        P(format_area(exterior.get("openings_area_m2")), "Cell"),
        P(format_area(exterior.get("net_area_m2")), "CellBold"),
    ])
    
    table = Table(rows, colWidths=[38*mm, 28*mm, 28*mm, 28*mm, 28*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("BACKGROUND", (0,0), (-1,0), COLORS["bg_header"]),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTNAME", (0,0), (-1,0), BOLD_FONT),
    ]))
    
    return table


def create_surfaces_table(surfaces_data: dict) -> Table:
    """Tabel suprafețe (podea, tavan, fundație, acoperiș)"""
    rows = [
        [P("Suprafață", "CellBold"), P("Arie (m²)", "CellBold")]
    ]
    
    items = [
        ("Fundație", surfaces_data.get("foundation_m2")),
        ("Podea Utilă", surfaces_data.get("floor_m2")),
        ("Tavan Util", surfaces_data.get("ceiling_m2")),
        ("Acoperiș (amprenta)", surfaces_data.get("roof_m2")),
    ]
    
    for label, value in items:
        if value and value > 0:
            rows.append([
                P(label, "Cell"),
                P(format_area(value), "CellBold")
            ])
    
    table = Table(rows, colWidths=[90*mm, 60*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("BACKGROUND", (0,0), (-1,0), COLORS["bg_header"]),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    
    return table


def create_openings_table(openings_data: list) -> Table:
    """Tabel deschideri (uși/ferestre) cu detalii complete"""
    rows = [
        [P("ID", "CellBold"), P("Tip", "CellBold"), 
         P("Status", "CellBold"), P("Lățime (m)", "CellBold")]
    ]
    
    for opening in openings_data:
        obj_type = opening.get("type", "unknown")
        status = opening.get("status", "unknown")
        width = opening.get("width_m", 0.0)
        obj_id = opening.get("id", "—")
        
        # Traduceri
        type_names = {
            "door": "Ușă Simplă",
            "double_door": "Ușă Dublă",
            "window": "Fereastră Simplă",
            "double_window": "Fereastră Dublă"
        }
        
        status_names = {
            "exterior": "Exterior",
            "interior": "Interior",
            "unknown": "Necunoscut"
        }
        
        rows.append([
            P(str(obj_id), "Cell"),
            P(type_names.get(obj_type, obj_type), "Cell"),
            P(status_names.get(status, status), "Cell"),
            P(f"{width:.2f}", "Cell")
        ])
    
    table = Table(rows, colWidths=[15*mm, 55*mm, 40*mm, 40*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("BACKGROUND", (0,0), (-1,0), COLORS["bg_header"]),
        ("ALIGN", (0,1), (0,-1), "CENTER"),
        ("ALIGN", (3,1), (3,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTSIZE", (0,1), (-1,-1), 8),
    ]))
    
    return table


def create_pricing_breakdown_table(pricing_data: dict) -> Table:
    """Tabel breakdown complet costuri"""
    breakdown = pricing_data.get("breakdown", {})
    
    rows = [
        [P("Categorie", "CellBold"), P("Detalii", "CellBold"), 
         P("Cost (EUR)", "CellBold")]
    ]
    
    categories = [
        ("foundation", "Fundație"),
        ("structure_walls", "Structură Pereți"),
        ("floors_ceilings", "Planșee și Tavane"),
        ("roof", "Acoperiș"),
        ("openings", "Tâmplărie"),
        ("finishes", "Finisaje"),
        ("utilities", "Utilități & Instalații"),
    ]
    
    for key, label in categories:
        data = breakdown.get(key, {})
        if not data:
            continue
        
        total_cost = data.get("total_cost", 0.0)
        items = data.get("items") or data.get("detailed_items") or []
        
        # Linia principală
        rows.append([
            P(label, "CellBold"),
            P(f"{len(items)} componente", "CellSmall"),
            P(format_money(total_cost), "CellBold")
        ])
        
        # Sublinii (primele 3 itemi ca exemplu)
        for item in items[:3]:
            item_name = item.get("name", item.get("category", "—"))
            item_cost = item.get("total_cost", item.get("cost", 0.0))
            
            rows.append([
                P("", "Cell"),
                P(f"  • {item_name}", "CellSmall"),
                P(format_money(item_cost), "CellSmall")
            ])
    
    # TOTAL
    total = pricing_data.get("total_cost_eur", 0.0)
    rows.append([
        P("TOTAL", "CellBold"),
        P("", "Cell"),
        P(format_money(total), "CellBold")
    ])
    
    table = Table(rows, colWidths=[50*mm, 70*mm, 40*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("BACKGROUND", (0,0), (-1,0), COLORS["bg_header"]),
        ("BACKGROUND", (0,-1), (-1,-1), COLORS["bg_light"]),
        ("ALIGN", (2,1), (2,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
    ]))
    
    return table


def create_totals_summary_table(totals: dict) -> Table:
    """Tabel rezumat final cu toate costurile"""
    rows = [
        [P("Descriere", "CellBold"), P("Valoare (EUR)", "CellBold")]
    ]
    
    items = [
        ("Fundație", totals.get("foundation", 0.0)),
        ("Structură", totals.get("structure", 0.0)),
        ("Planșee & Tavane", totals.get("floors_ceilings", 0.0)),
        ("Acoperiș", totals.get("roof", 0.0)),
        ("Tâmplărie", totals.get("openings", 0.0)),
        ("Finisaje", totals.get("finishes", 0.0)),
        ("Utilități", totals.get("utilities", 0.0)),
    ]
    
    subtotal = sum(v for _, v in items if v)
    
    for label, value in items:
        if value > 0:
            rows.append([P(label, "Cell"), P(format_money(value), "Cell")])
    
    rows.append([
        P("SUBTOTAL", "CellBold"),
        P(format_money(subtotal), "CellBold")
    ])
    
    # TVA (19%)
    vat = subtotal * 0.19
    total_with_vat = subtotal + vat
    
    rows.append([P("TVA (19%)", "Cell"), P(format_money(vat), "Cell")])
    rows.append([
        P("TOTAL FINAL", "CellBold"),
        P(format_money(total_with_vat), "CellBold")
    ])
    
    table = Table(rows, colWidths=[100*mm, 60*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, COLORS["border"]),
        ("BACKGROUND", (0,0), (-1,0), COLORS["bg_header"]),
        ("BACKGROUND", (0,-3), (-1,-3), COLORS["bg_light"]),
        ("BACKGROUND", (0,-1), (-1,-1), COLORS["success"]),
        ("TEXTCOLOR", (0,-1), (-1,-1), colors.white),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTSIZE", (0,-1), (-1,-1), 11),
    ]))
    
    return table