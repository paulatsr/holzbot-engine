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
    Separă elementele incluse de cele excluse în funcție de nivelul ofertei.
    """
    
    # Definire Pachete
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
        "detailed_breakdown": [],  # Elemente incluse
        "excluded_options": []     # Elemente excluse (doar sumar)
    }
    
    total_price = 0.0
    
    # Mapare chei backend -> Nume afișat
    category_config = [
        ("foundation", "Fundație"),
        ("structure_walls", "Structură Pereți"),
        ("floors_ceilings", "Planșee și Tavane"),
        ("roof", "Acoperiș"),
        ("openings", "Tâmplărie (Uși/Ferestre)"),
        ("finishes", "Finisaje"),
    ]
    
    breakdown = pricing_data.get("breakdown", {})
    
    for cat_key, cat_name in category_config:
        data = breakdown.get(cat_key, {})
        if not data:
            continue
            
        # Verifică dacă e inclus în pachet
        # Atenție: 'structure_walls' în mapare vs 'structure' în INCLUSIONS
        # Normalizăm cheia pentru verificare
        check_key = cat_key
        if cat_key == "structure_walls": check_key = "structure"
        
        is_included = selection.get(check_key, False)
        
        # Extragem lista de itemi detaliați
        items = data.get("items") or data.get("detailed_items") or []
        cat_total = data.get("total_cost", 0.0)
        
        if is_included:
            total_price += cat_total
            
            # Dacă avem items, îi punem pe toți. Dacă nu, un generic.
            if not items and cat_total > 0:
                items = [{
                    "name": cat_name,
                    "details": "Cost estimat global",
                    "total_cost": cat_total
                }]
            
            final_json["detailed_breakdown"].append({
                "category": cat_name,
                "total_category": cat_total,
                "items": items
            })
        else:
            # Doar sumar pentru opțiuni excluse
            if cat_total > 0:
                final_json["excluded_options"].append({
                    "category": cat_name,
                    "estimated_cost": cat_total,
                    "items_count": len(items)
                })

    final_json["summary"]["total_price_eur"] = round(total_price, 2)

    # Salvare
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_json, f, indent=2, ensure_ascii=False)
        
    return final_json