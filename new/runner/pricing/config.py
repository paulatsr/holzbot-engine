# new/runner/pricing/config.py
from __future__ import annotations
from pathlib import Path

# Calea către folderul cu JSON-uri (finish_coefficients.json etc.)
# Presupunem că sunt în new/runner/pricing/data/
DATA_DIR = Path(__file__).parent / "data"

FINISH_COEFFS_FILE = DATA_DIR / "finish_coefficients.json"
FOUNDATION_COEFFS_FILE = DATA_DIR / "foundation_coefficients.json"
OPENINGS_PRICES_FILE = DATA_DIR / "openings_prices.json"
SYSTEM_PREFAB_FILE = DATA_DIR / "system_prefab_coeffs.json"
AREA_COEFFS_FILE = DATA_DIR / "area_coefficients.json"