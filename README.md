# Options Scanner

A Python-based cash-secured put opportunity scanner.

- Pulls a watchlist CSV (`symbol_lists/watchlist.csv`).
- Retrieves nearest-expiry option chains via yfinance.
- Calculates Black-Scholes Greeks (`scanner/indicators.py`).
- Filters opportunities (`scanner/strategy_filters.py`).
- Flags high-yield puts.
- Includes a back-testing harness (`scanner/backtest.py`).

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # add Alpaca credentials (optional)

python cli.py                  # scan watchlist (default)
python cli.py --debug          # verbose watchlist scan
python cli.py scan             # full S&P 500 + Nasdaq-100 + watchlist scan
python cli.py scan --ticker AAPL
python cli.py export --format csv
python cli.py dashboard --html
python cli.py serve            # start Flask web dashboard
python cli.py serve --port 8080
```

## Project layout

```
Trading/
├─ scanner/                    # core library package
│   ├─ __init__.py
│   ├─ indicators.py           # Black-Scholes Greeks
│   ├─ option_chains.py        # yfinance fetcher + cache
│   ├─ strategy_filters.py     # screening & ranking logic
│   ├─ alpaca_config.py        # Alpaca credential loader
│   └─ backtest.py             # back-testing harness
├─ web/                        # Flask web dashboard
│   ├─ app.py
│   ├─ results_loader.py
│   ├─ templates/
│   └─ static/
├─ symbol_lists/               # universe definitions
│   ├─ watchlist.csv           # user watchlist (edit this)
│   ├─ sp500.json
│   └─ nasdaq100.json
├─ outputs/                    # timestamped scan results (CSV/JSON/HTML)
├─ data/cache/                 # option chain cache (auto-managed)
├─ logs/                       # scanner and dashboard logs
├─ docs/                       # planning docs
├─ cli.py                      # unified CLI entry point
├─ options_scanner.py          # full-universe scanner
├─ dashboard.py                # console/HTML dashboard renderer
├─ requirements.txt
└─ .env.example
```

## Running back-tests

1. Populate `historical_data/` with CSV files named `<ticker>_<date>.csv`.
2. Create `backtest_input.json` mapping tickers to `[["date", spot], ...]`.
3. Run `python -m scanner.backtest`.

## Development

Add unit tests under `tests/` and set up CI (GitHub Actions) to run them.

---

*For research and educational purposes only. Does not place trades.*
# OptionScanner
