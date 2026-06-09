"""
cli.py
------
Unified entry point for the cash-secured put options scanner.

Usage (from the project root)::

    python cli.py                  # Scan watchlist (default)
    python cli.py --debug          # Verbose watchlist scan
    python cli.py scan             # Full S&P 500 + Nasdaq-100 + watchlist scan
    python cli.py scan --ticker AAPL
    python cli.py export --format csv
    python cli.py test
    python cli.py dashboard --html
    python cli.py serve
    python cli.py serve --port 8080
"""

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

from symbol_lists.watchlist_parser import load_watchlist
from scanner.option_chains import get_option_chain
from scanner.strategy_filters import scan_tickers
from options_scanner import OptionsScanner
from dashboard import generate_dashboard


def _fetch_spot_price(ticker: str) -> float:
    """Return the latest regular-market price for *ticker*."""
    from scanner.yf_session import ticker as yf_ticker
    info = yf_ticker(ticker).info
    price = info.get("regularMarketPrice") or info.get("previousClose")
    if price is None:
        raise RuntimeError(f"Unable to obtain spot price for {ticker}")
    return float(price)


def cmd_watchlist(args: argparse.Namespace) -> int:
    """Run the modular watchlist scanner."""
    watch = load_watchlist()
    tickers = list(watch.keys())
    if not tickers:
        print("Watchlist is empty – add tickers to symbol_lists/watchlist.csv")
        return 1

    if args.debug:
        print(f"[debug] Scanning {len(tickers)} tickers: {', '.join(tickers)}")

    spot_prices: dict[str, float] = {}
    for t in tickers:
        try:
            spot_prices[t] = _fetch_spot_price(t)
            if args.debug:
                print(f"[debug] {t} spot price: {spot_prices[t]:.2f}")
        except Exception as exc:
            print(f"[WARN] Could not fetch spot for {t}: {exc}")
            continue

    if not spot_prices:
        print("No valid spot prices – aborting.")
        return 1

    chains: dict[str, pd.DataFrame] = {}
    for t in spot_prices:
        try:
            chains[t] = get_option_chain(t)
            if args.debug:
                print(f"[debug] {t} option chain: {len(chains[t])} contracts")
        except Exception as exc:
            print(f"[WARN] Failed to fetch option chain for {t}: {exc}")
            continue

    if not chains:
        print("No option chains retrieved – aborting.")
        return 1

    candidates, flagged = scan_tickers(chains, spot_prices)

    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 120)

    print("\n=== Regular Candidates ===")
    if candidates.empty:
        print("(none)")
    else:
        print(candidates[["ticker", "contract_symbol", "strike", "expiration", "bid", "ask", "risk_adj_yield", "distance_otm"]].to_string(index=False))

    print("\n=== Flagged (High-Yield) Opportunities ===")
    if flagged.empty:
        print("(none)")
    else:
        print(flagged[["ticker", "contract_symbol", "strike", "expiration", "bid", "ask", "risk_adj_yield", "distance_otm"]].to_string(index=False))

    return 0


def _latest_file(pattern: str) -> Optional[str]:
    """Return the most recent file matching the glob pattern, or None."""
    matches = glob.glob(pattern)
    if not matches:
        return None
    matches.sort(key=os.path.getmtime, reverse=True)
    return matches[0]


def _print_latest_files(csv: bool, json_: bool) -> None:
    """Print paths of the most recent CSV/JSON output files."""
    if csv:
        latest_csv = _latest_file("outputs/options_opportunities_*.csv")
        if latest_csv:
            print(f"Latest CSV: {latest_csv}")
        else:
            print("No CSV output files found.")
    if json_:
        latest_json = _latest_file("outputs/options_opportunities_*.json")
        if latest_json:
            print(f"Latest JSON: {latest_json}")
        else:
            print("No JSON output files found.")


def cmd_scan(args: argparse.Namespace) -> None:
    """Run the full universe scanner."""
    scanner = OptionsScanner()
    scanner.run_scan()

    if args.ticker:
        ticker = args.ticker.upper()
        latest_csv = _latest_file("outputs/options_opportunities_all_*.csv")
        if not latest_csv:
            print("No CSV output to filter – run a scan first.", file=sys.stderr)
            return

        df = pd.read_csv(latest_csv)
        filtered = df[df["symbol"].str.upper() == ticker]

        if filtered.empty:
            print(f"No qualifying puts found for ticker {ticker}.")
        else:
            print(f"\n=== {ticker} – qualifying puts (filtered from latest scan) ===")
            columns = [
                ("Symbol", 8), ("Current Price", 12), ("Strike", 8),
                ("Expiration", 12), ("Premium", 8), ("Delta", 8),
                ("OI", 8), ("Distance OTM %", 12),
                ("Annualized Yield %", 16), ("Risk-Adj Yield %", 16), ("Flagged", 8),
            ]
            header = "".join(f"{name:<{width}}" for name, width in columns)
            print(header)
            print("-" * len(header))
            for _, row in filtered.iterrows():
                row_data = [
                    f"{row.get('symbol', ''):<{columns[0][1]}}",
                    f"{row.get('current_price', 0):<{columns[1][1]}.2f}",
                    f"{row.get('strike', 0):<{columns[2][1]}.2f}",
                    f"{row.get('expiration', ''):<{columns[3][1]}}",
                    f"{row.get('premium', 0):<{columns[4][1]}.2f}",
                    f"{row.get('delta', 0):<{columns[5][1]}.2f}",
                    f"{int(row.get('open_interest', 0)):<{columns[6][1]}}",
                    f"{row.get('distance_otm', 0):<{columns[7][1]}.2f}",
                    f"{row.get('annualized_yield', 0):<{columns[8][1]}.2f}",
                    f"{row.get('risk_adjusted_yield', 0):<{columns[9][1]}.2f}",
                    f"{'YES' if row.get('flagged', False) else 'NO':<{columns[10][1]}}",
                ]
                print("".join(row_data))


def cmd_export(args: argparse.Namespace) -> None:
    """Print the path of the most recent output file of the requested format."""
    fmt = args.format.lower()
    if fmt == "csv":
        _print_latest_files(csv=True, json_=False)
    elif fmt == "json":
        _print_latest_files(csv=False, json_=True)
    else:
        print("Invalid format – use 'csv' or 'json'.", file=sys.stderr)


def cmd_test(_: argparse.Namespace) -> None:
    """Execute the bundled test_scanner.py script."""
    test_path = Path(__file__).parent / "test_scanner.py"
    if not test_path.is_file():
        print("test_scanner.py not found.", file=sys.stderr)
        sys.exit(1)
    subprocess.run([sys.executable, str(test_path)], check=False)


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Run a full scan and generate the dashboard."""
    generate_dashboard(html=args.html)


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the Flask web dashboard."""
    from web.app import app

    print(f"Starting dashboard at http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Cash-Secured Put Options Scanner",
    )
    parser.add_argument("--debug", action="store_true", help="Enable verbose output")

    subparsers = parser.add_subparsers(dest="command")

    p_watch = subparsers.add_parser(
        "watchlist",
        help="Scan symbol_lists/watchlist.csv (default when no subcommand is given).",
    )
    p_watch.set_defaults(func=cmd_watchlist)

    p_scan = subparsers.add_parser(
        "scan",
        help="Run the full S&P 500 + Nasdaq-100 + watchlist scanner.",
    )
    p_scan.add_argument(
        "--ticker",
        type=str,
        help="If set, filter the latest CSV results to this ticker only.",
    )
    p_scan.set_defaults(func=cmd_scan)

    p_export = subparsers.add_parser(
        "export",
        help="Show the path of the most recent output file.",
    )
    p_export.add_argument(
        "--format",
        choices=["csv", "json"],
        required=True,
        help="File format to export.",
    )
    p_export.set_defaults(func=cmd_export)

    p_test = subparsers.add_parser(
        "test",
        help="Run the quick test script (test_scanner.py).",
    )
    p_test.set_defaults(func=cmd_test)

    p_dash = subparsers.add_parser(
        "dashboard",
        help="Run scan and produce a console/dashboard view.",
    )
    p_dash.add_argument(
        "--html",
        action="store_true",
        help="Create the static HTML dashboard (saved to outputs/dashboard.html).",
    )
    p_dash.set_defaults(func=cmd_dashboard)

    p_serve = subparsers.add_parser(
        "serve",
        help="Start the interactive Flask web dashboard.",
    )
    p_serve.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=5000, help="Port to bind (default: 5000)")
    p_serve.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        return cmd_watchlist(args)

    result = args.func(args)
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
