# new/runner/offer_builder.py
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

def build_final_offer(
    pricing_data: dict, 
    offer_level: str, 
    output_path: Path
) -> dict:
    """
    Generează oferta finală detaliată (final_offer.json).
    
    offer_level: 'Structură' | 'Structură + ferestre' | 'Casă completă'
    """
    
    # 1. Definim ce categorii intră în fiecare nivel
    # (True = inclus, False = exclus/opțional)
    INCLUSIONS = {
        "Structură": {
            "foundation": True,
            "structure": True,
            "roof": True,
            "floors_ceilings": True,
            "openings": False,
            "finishes": False
        },
        "Structură + ferestre": {
            "foundation": True,
            "structure": True,
            "roof": True,
            "floors_ceilings": True,
            "openings": True,
            "finishes": False
        },
        "Casă completă": {
            "foundation": True,
            "structure": True,
            "roof": True,
            "floors_ceilings": True,
            "openings": True,
            "finishes": True
        }
    }
    
    # Fallback dacă nivelul nu e recunoscut
    selection = INCLUSIONS.get(offer_level, INCLUSIONS["Casă completă"])
    
    final_json = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "offer_level": offer_level
        },
        "summary": {
            "total_price_eur": 0.0,
            "currency": "EUR"
        },
        "detailed_breakdown": [],  # Lista plată cu TOATE elementele incluse
        "excluded_options": []     # Ce ar mai putea cumpăra
    }
    
    total_price = 0.0
    
    # 2. Iterăm prin categorii și construim listele
    # Ordinea contează pentru afișare logică
    categories_order = ["foundation", "structure", "floors_ceilings", "roof", "openings", "finishes"]
    
    category_names_ro = {
        "foundation": "Fundație",
        "structure": "Structură Pereți",
        "floors_ceilings": "Planșee și Tavane",
        "roof": "Acoperiș",
        "openings": "Tâmplărie (Uși/Ferestre)",
        "finishes": "Finisaje"
    }
    
    for cat_key in categories_order:
        data = pricing_data.get(cat_key, {})
        if not data: continue
        
        is_included = selection.get(cat_key, False)
        
        # Extragem lista de itemi (unii au 'items', alții 'detailed_items')
        items = data.get("items") or data.get("detailed_items") or []
        
        # Dacă e categorie simplă (fără sub-itemi mulți), creăm un item sintetic
        if not items and data.get("total_cost", 0) > 0:
            items = [{
                "name": category_names_ro[cat_key],
                "details": "Cost estimat global",
                "total_cost": data["total_cost"]
            }]
            
        if is_included:
            # Adăugăm la total
            total_price += data.get("total_cost", 0.0)
            
            # Adăugăm secțiune în breakdown
            section = {
                "category": category_names_ro[cat_key],
                "total_category": data.get("total_cost", 0.0),
                "items": items  # AICI E DETALIUL MAXIM (fiecare geam, fiecare strat de acoperiș)
            }
            final_json["detailed_breakdown"].append(section)
        else:
            # Adăugăm la excluse (doar sumar)
            final_json["excluded_options"].append({
                "category": category_names_ro[cat_key],
                "estimated_cost": data.get("total_cost", 0.0),
                "items_count": len(items)
            })

    final_json["summary"]["total_price_eur"] = round(total_price, 2)

    # 3. Salvare
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_json, f, indent=2, ensure_ascii=False)
        
    return final_json