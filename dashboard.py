#!/usr/bin/env python3
"""
Dashboard module for the cash‑secured put scanner.

* Calls OptionsScanner().run_scan() (which creates timestamped CSV/JSON files)
* Loads the **latest** CSV output that the scanner produced
* Extracts the three 10‑item sections that the scanner already builds:
    – safest
    – highest_yield
    – balanced
* Prints a nicely‑formatted console view (rich if installed, else pandas)
* Optionally writes a static HTML page (dashboard.html) in the project’s
  top‑level `outputs/` folder.
"""

import os
import datetime
import logging
from typing import List, Dict

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    RICH_AVAILABLE = True
except Exception:
    RICH_AVAILABLE = False

import pandas as pd

from options_scanner import OptionsScanner
from web.results_loader import latest_scan_csv_path, load_sections_for_csv

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "outputs"))
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "logs"))
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

LOGGER = logging.getLogger("dashboard")
LOGGER.setLevel(logging.INFO)
log_handler = logging.FileHandler(os.path.join(LOG_DIR, "dashboard.log"))
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_handler.setFormatter(log_formatter)
if not LOGGER.handlers:
    LOGGER.addHandler(log_handler)


def _render_console(csv_path: str, sections: Dict[str, List[Dict]]) -> None:
    total_opps = pd.read_csv(csv_path).shape[0]
    flagged = pd.read_csv(csv_path)["flagged"].sum()

    scan_time = datetime.datetime.fromtimestamp(
        os.path.getmtime(csv_path)
    ).strftime("%Y-%m-%d %H:%M:%S")

    if RICH_AVAILABLE:
        console = Console()
        console.print(Panel.fit(
            f"[bold]Cash‑Secured Put Dashboard[/bold]\n"
            f"[green]Scan time:[/] {scan_time}\n"
            f"[green]Total opportunities:[/] {total_opps}\n"
            f"[green]Flagged trades:[/] {flagged}",
            title="📊 Summary",
            border_style="blue",
        ))

        def _rich_table(title: str, data: List[Dict]) -> Table:
            if not data:
                tbl = Table(title=title, show_header=False)
                tbl.add_row("No data")
                return tbl

            cols = list(data[0].keys())
            tbl = Table(title=title, box=box.MINIMAL_DOUBLE_HEAD, header_style="bold magenta")
            for col in cols:
                tbl.add_column(col, justify="right", no_wrap=True)

            for row in data:
                vals = [str(row.get(c, "")) for c in cols]
                tbl.add_row(*vals)
            return tbl

        console.print(_rich_table("Top 10 Safest", sections.get("safest", [])))
        console.print(_rich_table("Top 10 Highest Yield", sections.get("highest_yield", [])))
        console.print(_rich_table("Top 10 Balanced", sections.get("balanced", [])))
    else:
        print("\n=== Cash‑Secured Put Dashboard ===")
        print(f"Scan time          : {scan_time}")
        print(f"Total opportunities: {total_opps}")
        print(f"Flagged trades     : {flagged}\n")

        for name, rows in sections.items():
            print(f"--- Top 10 {name.replace('_', ' ').title()} ---")
            df = pd.DataFrame(rows)
            print(df.to_string(index=False))
            print()


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Cash‑Secured Put Dashboard</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2rem; color:#333; }}
h1 {{ color:#2c3e50; }}
.summary {{ margin-bottom:1.5rem; }}
table {{ border-collapse:collapse; width:100%; margin-bottom:2rem; }}
th, td {{ border:1px solid #ddd; padding:0.5rem; text-align:right; }}
th {{ background:#f4f4f4; }}
tr:nth-child(even) {{ background:#fafafa; }}
.high-yield {{ background:#e8f5e9; }}
.high-risk {{ background:#ffebee; }}
</style>
</head>
<body>
<h1>Cash‑Secured Put Dashboard</h1>
<div class="summary">
<p><strong>Scan time:</strong> {scan_time}</p>
<p><strong>Total opportunities:</strong> {total_opps}</p>
<p><strong>Flagged trades:</strong> {flagged}</p>
</div>

{tables}
</body>
</html>
"""


def _render_html(csv_path: str, sections: Dict[str, List[Dict]]) -> str:
    total_opps = pd.read_csv(csv_path).shape[0]
    flagged = pd.read_csv(csv_path)["flagged"].sum()
    scan_time = datetime.datetime.fromtimestamp(
        os.path.getmtime(csv_path)
    ).strftime("%Y-%m-%d %H:%M:%S")

    def _section_to_html(title: str, rows: List[Dict]) -> str:
        if not rows:
            return f"<h2>{title}</h2><p>No data</p>"
        df = pd.DataFrame(rows)

        if "risk_adjusted_yield" in df.columns:
            df["risk_adjusted_yield"] = df["risk_adjusted_yield"].apply(
                lambda x: f'<span class="high-yield">{x:.2f}</span>'
            )
        if "delta" in df.columns:
            df["delta"] = df["delta"].apply(
                lambda x: f'<span class="high-risk">{x:.2f}</span>' if abs(x) > 0.25 else f"{x:.2f}"
            )

        html = df.to_html(
            index=False,
            border=0,
            classes="dashboard",
            escape=False,
        )
        return f"<h2>{title}</h2>{html}"

    tables_html = "\n".join(
        _section_to_html("Top 10 Safest", sections.get("safest", []))
        + _section_to_html("Top 10 Highest Yield", sections.get("highest_yield", []))
        + _section_to_html("Top 10 Balanced", sections.get("balanced", []))
    )

    return HTML_TEMPLATE.format(
        scan_time=scan_time,
        total_opps=total_opps,
        flagged=flagged,
        tables=tables_html,
    )


def generate_dashboard(html: bool = False) -> None:
    """
    Run the scanner, locate the latest CSV output, extract the three sections,
    and render either a console view or a static HTML file.
    """
    LOGGER.info("Dashboard generation started")
    try:
        scanner = OptionsScanner()
        scanner.run_scan()

        csv_path = latest_scan_csv_path()
        if not csv_path:
            raise FileNotFoundError("No scanner CSV output found after run_scan().")

        sections = load_sections_for_csv(csv_path)
        _render_console(csv_path, sections)

        if html:
            html_content = _render_html(csv_path, sections)
            out_path = os.path.join(OUTPUT_DIR, "dashboard.html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            LOGGER.info(f"Dashboard HTML written to {out_path}")
            print(f"\nHTML dashboard saved to: {out_path}")

        LOGGER.info("Dashboard generation completed successfully")
    except Exception:
        LOGGER.exception("Dashboard generation failed")
        raise


if __name__ == "__main__":
    generate_dashboard(html=True)
