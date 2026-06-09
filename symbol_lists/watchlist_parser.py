"""
watchlist_parser.py
-------------------
Utility to read a user‑provided watchlist CSV.

Expected CSV columns (case‑insensitive):
    ticker, company_name, sector, weight
Only the ``ticker`` column is required – missing columns are filled
with defaults.

Returns a dict mapping ticker → metadata dict, e.g.:
{
    "AAPL": {"company_name": "Apple Inc.", "sector": "Technology", "weight": 0.0},
    "MSFT": {...}
}
"""

import csv
from pathlib import Path
from typing import Dict, Any

DEFAULT_SECTOR = "Unspecified"
DEFAULT_WEIGHT = 0.0
DEFAULT_COMPANY = ""


def _clean(val: str) -> str:
    """Strip whitespace; return empty string if value is missing."""
    return val.strip() if val and val.strip() else ""


def read_watchlist(csv_path: Path) -> Dict[str, Dict[str, Any]]:
    """Read a watchlist CSV and return a ticker‑keyed dict.

    Parameters
    ----------
    csv_path: Path
        Path to the watchlist CSV.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"Watchlist file not found: {csv_path}")

    watchlist: Dict[str, Dict[str, Any]] = {}
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        # Normalize header names to lower‑case for flexibility
        header = {k.lower(): k for k in reader.fieldnames or []}
        for row in reader:
            ticker = _clean(row.get(header.get("ticker", "ticker"), ""))
            if not ticker:
                continue  # skip empty rows
            watchlist[ticker] = {
                "company_name": _clean(
                    row.get(header.get("company_name", "company_name"), DEFAULT_COMPANY)
                ),
                "sector": _clean(
                    row.get(header.get("sector", "sector"), DEFAULT_SECTOR)
                ),
                "weight": float(
                    _clean(
                        row.get(header.get("weight", "weight"), str(DEFAULT_WEIGHT))
                    ) or DEFAULT_WEIGHT
                ),
            }
    return watchlist


def load_watchlist() -> Dict[str, Dict[str, Any]]:
    """Convenience helper – loads ``watchlist.csv`` from the same folder."""
    csv_path = Path(__file__).with_name("watchlist.csv")
    return read_watchlist(csv_path)


if __name__ == "__main__":
    try:
        wl = load_watchlist()
        print(f"Loaded {len(wl)} tickers from watchlist.csv")
    except Exception as e:
        print(f"Error loading watchlist: {e}")
