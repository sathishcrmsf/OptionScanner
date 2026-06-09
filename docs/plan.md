# Options Put‑Scanner – System Architecture & Documentation

## 1. Overview
The **Cash‑Secured Put Options Scanner** is a research‑only Python project that:

1. Retrieves a universe of tickers (S&P 500, Nasdaq‑100, optional watchlist).
2. Pulls current stock data and the **long‑dated PUT options chain** for each ticker using **yfinance**.
3. Calculates financial metrics for each put contract.
4. Applies a strict set of **filters** to keep only cash‑secured put candidates.
5. Ranks the remaining contracts by **risk‑adjusted yield**, then **open interest**, then **delta magnitude**.
6. Generates three summary sections (safest, highest‑yield, balanced) and writes the results to:
   * Console tables
   * CSV files
   * JSON files  

The scanner is purely **research‑oriented** – it never places orders.  Alpaca credentials are loaded via `alpaca_config.py` for future execution integration but are **not used** by the current pipeline.

---

## 2. File Structure & Responsibilities

```
/Trading
│
├─ options_scanner.py      # Core scanner implementation (all logic)
├─ cli.py                  # Thin command‑line wrapper (new)
├─ test_scanner.py         # Small sanity‑check script
├─ alpaca_config.py        # Helper to load Alpaca credentials (future use)
├─ requirements.txt        # Python dependencies
├─ watchlist.txt           # Optional user‑provided ticker list
├─ .env.example            # Example environment file (API keys, etc.)
├─ README.md               # User guide (new)
└─ plan.md                 # Architecture documentation (this file)
```

* **options_scanner.py** – defines `OptionsScanner` with methods for data acquisition, metric calculation, filtering, ranking, summarising, and file output.
* **cli.py** – exposes the scanner via a simple CLI (`scan`, `scan --ticker`, `export`, `test`).
* **test_scanner.py** – runs the scanner on a hard‑coded subset (`AAPL`, `MSFT`, `GOOGL`) and saves the outputs.
* **alpaca_config.py** – provides `get_alpaca_credentials()` (not invoked yet).
* **requirements.txt** – lists all external libraries (`yfinance`, `pandas`, `numpy`, `requests`, `alpaca‑trade‑api`, `backtrader`, `python‑dotenv`).

---

## 3. Data Flow

```
┌─────────────────────┐
│  Universe Sources    │
│  – S&P 500 (Wiki)   │
│  – Nasdaq‑100 (Wiki)│
│  – watchlist.txt    │
└───────┬─────────────┘
        │  (list of ticker symbols)
        ▼
┌─────────────────────┐
│  OptionsScanner      │
│  (instantiated)     │
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  get_stock_data()   │   ← yfinance → ticker.info / history
│  (price, avg volume)│
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  get_options_chain()│   ← yfinance → option_chain(expiration)
│  (PUTs, farthest ≥12‑mo)│
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  calculate_metrics()│   • Uses row fields: strike, bid, ask, delta,
│                      │     openInterest, expiration
│                      │   • Requires current_stock_price
│                      │   • Returns a dict of all metrics (see formulas)
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  filter_options()   │   Applies every filter (see §4)
│  → list of dicts    │   (one dict per qualifying put)
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  scan_universe()    │   Loops over all tickers, accumulates all
│  qualifying puts    │   qualified options in a master list
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  rank_opportunities()│   Sorts by risk‑adjusted yield ↓,
│                      │   open interest ↓, |delta| ↑
│  → ranked list      │
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  flag_exceptional_  │   Marks contracts that meet the
│  opportunities()   │   “exceptional” thresholds
│  → flagged list    │
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  generate_summary_ │   Builds three 10‑item sections:
│  sections()         │   * safest *
│                     │   * highest_yield *
│                     │   * balanced *
│  → dict of sections│
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│  Output Layer       │
│  – print_console_table()  (top‑20 & flagged)
│  – save_to_csv()   (master, flagged, each section)
│  – save_to_json()  (same as CSV)
│  Files named with a timestamp:
│      options_opportunities_all_YYYYMMDD_HHMMSS.csv
│      …_flagged_… .json, etc.
└─────────────────────┘
```

---

## 4. Formulas (exact code implementation)

| Metric | Formula (as in `calculate_metrics`) |
|--------|--------------------------------------|
| **Premium** | `premium = (bid + ask) / 2` |
| **Years to expiration** | `years_to_expiration = max(days_to_expiration / 365.0, 0.001)` |
| **Annualized Yield** | `annualized_yield = (premium / strike) / years_to_expiration * 100` |
| **Risk‑Adjusted Yield** | `risk_adjusted_yield = (premium / (strike - premium)) / years_to_expiration * 100` |
| **Distance OTM %** | `distance_otm = ((stock_price - strike) / stock_price) * 100` |
| **Bid‑Ask spread % of premium** | `bid_ask_spread_pct = (ask - bid) / premium` |
| **Flagged criteria** (see `flag_exceptional_opportunities`) | `risk_adjusted_yield > 10.0`  <br> `distance_otm > 15.0`  <br> `delta > -0.20` (delta is negative) <br> `open_interest > 500` |

---

## 5. Filters (exact logic in `filter_options`)

| Filter | Condition (code) | Effect |
|--------|------------------|--------|
| Minimum average daily volume | `avg_volume < self.min_avg_volume` (1 M) → **exclude** |
| Expiration at least 12 months | `metrics['days_to_expiration'] < self.min_days_to_expiration` → **exclude** |
| Strike must be **below** current price | `metrics['strike'] >= stock_price` → **exclude** |
| Delta between –0.30 and –0.10 | `self.delta_min <= metrics['delta'] <= self.delta_max` (‑0.30 ≤ delta ≤ ‑0.10) |
| Open interest ≥ 100 | `metrics['open_interest'] < self.min_open_interest` → **exclude** |
| Bid‑ask spread ≤ 10 % of premium | `metrics['bid_ask_spread_pct'] >= self.max_bid_ask_spread_pct` → **exclude** |
| (All rows that pass are kept.) |

---

## 6. Runtime & Execution

### Prerequisites
* Python 3.9+ (tested on 3.11)
* Packages listed in `requirements.txt` (install via `pip install -r requirements.txt`)
* (Optional) Alpaca API keys in `.env` – scanner works without them.

### How to run

```bash
# Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy example env (optional)
cp .env.example .env
# edit .env if you have Alpaca keys; otherwise leave as‑is

# Full scan (covers S&P 500 + Nasdaq‑100 + watchlist)
python cli.py scan

# Scan a single ticker (wrapper post‑filters results)
python cli.py scan --ticker WMT

# Export the most recently generated CSV or JSON files
python cli.py export --format csv   # or --format json

# Run the quick test suite
python cli.py test
```

*The CLI simply forwards to `OptionsScanner().run_scan()` and then applies any requested post‑filters.*

### Output files (timestamped)

| File pattern | Description |
|--------------|-------------|
| `options_opportunities_all_YYYYMMDD_HHMMSS.csv` | All qualifying puts, ranked. |
| `options_opportunities_all_YYYYMMDD_HHMMSS.json` | Same data in JSON. |
| `options_opportunities_flagged_*.csv` / `.json` | Sub‑set flagged as “exceptional”. |
| `options_opportunities_safest_*.csv` / `.json` | Top‑10 safest (high OI, low \|Δ\|). |
| `options_opportunities_highest_yield_*.csv` / `.json` | Top‑10 highest risk‑adjusted yield. |
| `options_opportunities_balanced_*.csv` / `.json` | Top‑10 balanced (weighted score). |
| `options_scanner.log` | Execution log (INFO + warnings). |

---

## 7. Limitations (Current)

| Limitation | Reason |
|-----------|--------|
| **Only yfinance** for options data | No Polygon/Tradier integration yet (placeholder for future adapter). |
| **Long‑dated puts limited to the farthest expiration ≥12 mo** | Doesn’t scan multiple expirations beyond the farthest one. |
| **No live Alpaca execution** | Credentials are loaded but never used. |
| **Single‑threaded scanning** | Scans tickers sequentially; performance could be improved with parallelism. |
| **Static filter thresholds** | All filter values are hard‑coded in `OptionsScanner.__init__`. |
| **No automated alerting** | Outputs are files; no email/Slack/notification channel. |

---

## 8. Future Upgrade Paths (short roadmap)

1. **Polygon/Tradier provider** – replace `get_options_chain` with a class that calls a market‑data API, preserving the same DataFrame schema.
2. **Alpaca order execution** – after a successful research pass, call `alpaca_config.get_alpaca_credentials()` and use `alpaca‑trade‑api` to submit cash‑secured‑put orders.
3. **Parallel ticker processing** – `concurrent.futures.ThreadPoolExecutor` around `scan_stock`.
4. **CLI enhancements** – `argparse` for full filter overrides, custom output directories, and CSV/JSON naming control.
5. **Docker / CI pipeline** – containerise for scheduled runs (e.g., daily cron job).
6. **Rich reporting** – HTML report with charts, optional Jupyter notebook integration.

*End of plan.md*
