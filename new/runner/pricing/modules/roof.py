def calculate_roof_details(roof_result_data: dict) -> dict:
    """
    Transformă output-ul complex din etapa 'roof' într-o listă simplă de items pentru pricing.
    """
    components = roof_result_data.get("components", {})
    total = roof_result_data.get("roof_final_total_eur", 0.0)
    
    items = []
    
    # Mapăm componentele din roof_result.json
    # 1. Baza
    base = components.get("roof_base", {})
    if base:
        items.append({
            "category": "roof_base",
            "name": "Șarpantă și Montaj",
            "details": base.get("description", ""),
            "cost": base.get("average_total_eur", 0.0)
        })
        
    # 2. Tinichigerie
    sheet = components.get("sheet_metal", {})
    if sheet:
        items.append({
            "category": "roof_sheet_metal",
            "name": "Tinichigerie (Jgheaburi/Burlane)",
            "details": sheet.get("description", ""),
            "cost": sheet.get("total_eur", 0.0)
        })
        
    # 3. Extra Walls (ex: lucarne)
    extra = components.get("extra_walls", {})
    if extra and extra.get("total_eur", 0) > 0:
        items.append({
            "category": "roof_extra_walls",
            "name": "Pereți Suplimentari Acoperiș",
            "details": extra.get("description", ""),
            "cost": extra.get("total_eur", 0.0)
        })
        
    # 4. Insulation
    ins = components.get("insulation", {})
    if ins:
        items.append({
            "category": "roof_insulation",
            "name": "Izolație Acoperiș",
            "details": ins.get("description", ""),
            "cost": ins.get("total_eur", 0.0)
        })
        
    # 5. Material (Tigla/Tabla)
    mat = components.get("material", {})
    if mat:
        items.append({
            "category": "roof_cover",
            "name": "Învelitoare (Material)",
            "details": mat.get("description", ""),
            "cost": mat.get("total_eur", 0.0)
        })

    return {
        "total_cost": total,
        "detailed_items": items
    }