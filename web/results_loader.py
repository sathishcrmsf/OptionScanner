"""
Shared utilities for discovering and loading scan result files.
"""

from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ALL_PATTERN = re.compile(r"^options_opportunities_all_(\d{8}_\d{6})\.(json|csv)$")
META_PATTERN = re.compile(r"^options_opportunities_meta_(\d{8}_\d{6})\.json$")
SECTION_NAMES = ("safest", "highest_yield", "balanced")


def _scan_dir() -> str:
    return os.path.join(PROJECT_ROOT, "outputs")


def _parse_timestamp(filename: str) -> Optional[str]:
    match = ALL_PATTERN.match(filename)
    return match.group(1) if match else None


def list_scans() -> List[Dict[str, Any]]:
    """Return available scans sorted newest-first."""
    folder = _scan_dir()
    seen: Dict[str, Dict[str, Any]] = {}

    for ext in ("json", "csv"):
        pattern = os.path.join(folder, f"options_opportunities_all_*.{ext}")
        for path in glob.glob(pattern):
            ts = _parse_timestamp(os.path.basename(path))
            if not ts:
                continue
            mtime = os.path.getmtime(path)
            existing = seen.get(ts)
            if existing is None or mtime > existing["mtime"]:
                seen[ts] = {
                    "timestamp": ts,
                    "mtime": mtime,
                    "scan_time": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "path": path,
                }

    scans = list(seen.values())
    scans.sort(key=lambda s: s["mtime"], reverse=True)
    return scans


def _load_all_records(timestamp: str) -> List[Dict[str, Any]]:
    folder = _scan_dir()
    json_path = os.path.join(folder, f"options_opportunities_all_{timestamp}.json")
    csv_path = os.path.join(folder, f"options_opportunities_all_{timestamp}.csv")

    if os.path.isfile(json_path):
        with open(json_path, encoding="utf-8") as f:
            return json.load(f)

    if os.path.isfile(csv_path):
        df = pd.read_csv(csv_path)
        if "flagged" in df.columns:
            df["flagged"] = df["flagged"].map(
                lambda v: v is True or str(v).lower() in ("true", "1", "yes")
            )
        return df.to_dict(orient="records")

    raise FileNotFoundError(f"No scan data found for timestamp {timestamp}")


def _load_section_file(timestamp: str, section: str) -> Optional[List[Dict[str, Any]]]:
    folder = _scan_dir()
    for ext in ("json", "csv"):
        path = os.path.join(folder, f"options_opportunities_{section}_{timestamp}.{ext}")
        if not os.path.isfile(path):
            continue
        if ext == "json":
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        df = pd.read_csv(path)
        if "flagged" in df.columns:
            df["flagged"] = df["flagged"].map(
                lambda v: v is True or str(v).lower() in ("true", "1", "yes")
            )
        return df.to_dict(orient="records")
    return None


def _derive_sections(all_records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    if not all_records:
        return {name: [] for name in SECTION_NAMES}

    df_all = pd.DataFrame(all_records)

    df_all = df_all.copy()
    df_all["abs_delta"] = df_all["delta"].abs()
    safest_df = df_all.sort_values(
        by=["open_interest", "abs_delta", "risk_adjusted_yield"],
        ascending=[False, True, False],
    )
    highest_yield_df = df_all.sort_values(
        by=["risk_adjusted_yield", "open_interest", "abs_delta"],
        ascending=[False, False, True],
    )

    # "Balanced" = Income Efficiency: premium income per day per $1k capital at
    # risk. DTE-neutral, capital-normalized. Liquidity is a gate (OI>=500), not a
    # score. Mirrors the frontend incomeEfficiency() metric.
    cap = (df_all["capital_required"]
           if "capital_required" in df_all.columns
           else df_all["strike"] * 100).replace(0, pd.NA)
    days = df_all["days_to_expiration"].replace(0, pd.NA)
    df_all["income_efficiency"] = (
        (df_all["premium"] * 100) / cap / days * 1000
    ).fillna(0)
    balanced_df = df_all[df_all["open_interest"] >= 500].sort_values(
        by="income_efficiency", ascending=False
    )
    if balanced_df.empty:  # fall back if nothing clears the OI gate
        balanced_df = df_all.sort_values(by="income_efficiency", ascending=False)

    return {
        "safest": safest_df.head(10).to_dict(orient="records"),
        "highest_yield": highest_yield_df.head(10).to_dict(orient="records"),
        "balanced": balanced_df.head(10).to_dict(orient="records"),
    }


def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(record)
    if "flagged" in out:
        out["flagged"] = out["flagged"] is True or str(out["flagged"]).lower() in ("true", "1", "yes")
    return out


def load_scan(timestamp: Optional[str] = None) -> Dict[str, Any]:
    """Load a full scan payload for the given timestamp (latest if None)."""
    scans = list_scans()
    if not scans:
        raise FileNotFoundError("No scan results found. Run a scan first.")

    if timestamp is None:
        timestamp = scans[0]["timestamp"]
    else:
        if not any(s["timestamp"] == timestamp for s in scans):
            raise FileNotFoundError(f"No scan results found for timestamp {timestamp}")

    all_records = [_normalize_record(r) for r in _load_all_records(timestamp)]
    flagged = [r for r in all_records if r.get("flagged")]

    sections: Dict[str, List[Dict[str, Any]]] = {}
    for name in SECTION_NAMES:
        section_data = _load_section_file(timestamp, name)
        sections[name] = (
            [_normalize_record(r) for r in section_data[:10]]
            if section_data
            else _derive_sections(all_records)[name]
        )

    flagged_file = _load_section_file(timestamp, "flagged")
    if flagged_file is not None:
        flagged = [_normalize_record(r) for r in flagged_file]

    scan_meta = next(s for s in scans if s["timestamp"] == timestamp)
    unique_symbols = len({r.get("symbol") for r in all_records if r.get("symbol")})

    # Load DTE window from metadata file if present
    meta_path = os.path.join(_scan_dir(), f"options_opportunities_meta_{timestamp}.json")
    dte_min, dte_max = 1, 730
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            m = json.load(f)
            dte_min = m.get("dte_min", 1)
            dte_max = m.get("dte_max", 730)

    return {
        "timestamp": timestamp,
        "scan_time": scan_meta["scan_time"],
        "summary": {
            "scan_time": scan_meta["scan_time"],
            "total_opportunities": len(all_records),
            "flagged_count": len(flagged),
            "unique_symbols": unique_symbols,
            "dte_min": dte_min,
            "dte_max": dte_max,
        },
        "results": all_records,
        "flagged": flagged,
        "safest": sections["safest"],
        "highest_yield": sections["highest_yield"],
        "balanced": sections["balanced"],
    }


def load_latest_scan() -> Dict[str, Any]:
    return load_scan(None)


def latest_scan_csv_path() -> Optional[str]:
    """Return path to the newest master CSV file (for legacy dashboard HTML)."""
    folder = _scan_dir()
    matches = glob.glob(os.path.join(folder, "options_opportunities_all_*.csv"))
    if not matches:
        return None
    matches.sort(key=os.path.getmtime, reverse=True)
    return matches[0]


def load_sections_for_csv(csv_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Load section data using a master CSV path (legacy dashboard helper)."""
    filename = os.path.basename(csv_path)
    ts = _parse_timestamp(filename)
    if ts:
        payload = load_scan(ts)
        return {
            "safest": payload["safest"],
            "highest_yield": payload["highest_yield"],
            "balanced": payload["balanced"],
        }

    df_all = pd.read_csv(csv_path)
    return _derive_sections(df_all.to_dict(orient="records"))
