# new/runner/pricing/config.py
from __future__ import annotations
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# Existente
FINISH_COEFFS_FILE = DATA_DIR / "finish_coefficients.json"
FOUNDATION_COEFFS_FILE = DATA_DIR / "foundation_coefficients.json"
OPENINGS_PRICES_FILE = DATA_DIR / "openings_prices.json"
SYSTEM_PREFAB_FILE = DATA_DIR / "system_prefab_coeffs.json"
AREA_COEFFS_FILE = DATA_DIR / "area_coefficients.json"

# ✨ NOI - Utilități
ELECTRICITY_COEFFS_FILE = DATA_DIR / "electricity_coefficients.json"
HEATING_COEFFS_FILE = DATA_DIR / "heating_coefficients.json"
VENTILATION_COEFFS_FILE = DATA_DIR / "ventilation_coefficients.json"
SEWAGE_COEFFS_FILE = DATA_DIR / "sewage_coefficients.json"