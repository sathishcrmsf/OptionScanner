# Cash-Secured Put Options Scanner — Project Plan

## What This Project Does

This is a **research and screening tool** for finding cash-secured put (CSP) selling opportunities
across large-cap US equities. It does **not place trades** — it identifies, ranks, and presents
put contracts that meet a defined set of quality criteria, so you can manually review and execute
them on a brokerage like Robinhood.

### The core strategy

A cash-secured put is when you sell a put option and hold enough cash in your account to buy
100 shares at the strike price if the option is exercised (assigned). You collect the premium
upfront. The goal is to:

- Sell puts that are unlikely to be assigned (out-of-the-money, low delta)
- On stocks you would actually be happy to own at the strike price
- With enough premium to generate a meaningful annualized yield on the cash held

---

## How It Works — End-to-End Flow

```
Symbol universe           Data fetch           Filtering              Output
─────────────────   →   ────────────   →   ──────────────────   →   ────────────────
S&P 500 (~500)          yfinance            ≥ 12 months to           Ranked CSV/JSON
Nasdaq-100 (~100)       option chains       expiry                   Web dashboard
User watchlist          Greeks (B-S)        Delta -0.10 to -0.30     Console tables
                        cached daily        OI ≥ 100                 HTML report
                                            Bid-ask spread ≤ 10%
                                            Avg volume ≥ 1M shares
```

### Step 1 — Build the universe (`options_scanner.py`)

The scanner loads three symbol lists:
- **S&P 500** — from `symbol_lists/sp500.json` (falls back to Wikipedia scrape)
- **Nasdaq-100** — from `symbol_lists/nasdaq100.json` (falls back to Wikipedia scrape)
- **User watchlist** — from `symbol_lists/watchlist.csv` (edit this to add your own tickers)

All three are deduplicated into a single list of ~600 tickers.

### Step 2 — Fetch stock data and option chains (`scanner/option_chains.py`)

For each ticker, yfinance is queried for:
- Current market price and 30-day average volume
- PUT option chains for expirations ≥ 12 months out

Chains are cached in `data/cache/<ticker>_<expiry>.json` to avoid redundant API calls within the same day.

### Step 3 — Calculate Greeks (`scanner/indicators.py`)

When yfinance does not return delta (common), the module computes all five Black-Scholes Greeks
from scratch using the standard closed-form formula:

| Greek | Formula input | Meaning for CSP |
|-------|--------------|-----------------|
| Delta | Spot, Strike, T, σ, r | Proxy for assignment probability |
| Gamma | — | Rate of delta change |
| Vega  | — | Sensitivity to IV changes |
| Theta | — | Daily time-decay (positive for sellers) |
| Rho   | — | Interest rate sensitivity |

Risk-free rate defaults to **2.54%** (configurable).

### Step 4 — Apply screening filters (`scanner/strategy_filters.py`)

Each contract must pass **all** of the following:

| Filter | Value | Rationale |
|--------|-------|-----------|
| Option type | PUT only | Strategy is put-selling |
| Days to expiration | ≥ 365 days | LEAPS — maximises premium per dollar |
| Strike | Below current price | Must be out-of-the-money |
| Delta | −0.30 to −0.10 | Low assignment probability |
| Open interest | ≥ 100 contracts | Minimum liquidity |
| Bid-ask spread | ≤ 10% of premium | Avoid wide-spread traps |
| Avg daily volume | ≥ 1,000,000 shares | Liquid underlying only |

### Step 5 — Rank and score (`options_scanner.py`)

All qualifying contracts are ranked by:

1. **Risk-adjusted yield** (descending) — annualized `premium / (strike - premium)`
2. **Open interest** (descending) — liquidity tiebreaker
3. **|Delta|** (ascending) — lower probability of assignment breaks further ties

Three curated top-10 lists are generated:

| View | Sort logic |
|------|-----------|
| **Safest** | Highest OI → lowest |delta| → highest yield |
| **Highest Yield** | Highest risk-adj yield → highest OI → lowest |delta| |
| **Balanced** | Weighted score: 40% yield + 30% OI + 30% (1 − |delta|) |

### Step 6 — Flag exceptional opportunities

Contracts meeting **all four** criteria are flagged as "exceptional":

- Risk-adjusted yield > **10%**
- Distance OTM > **15%**
- Delta > **−0.20** (i.e., |delta| < 0.20)
- Open interest ≥ **500**

### Step 7 — Save outputs (`outputs/`)

Each scan run produces timestamped files in `outputs/`:

```
outputs/
  options_opportunities_all_YYYYMMDD_HHMMSS.csv    ← every qualifying contract
  options_opportunities_all_YYYYMMDD_HHMMSS.json
  options_opportunities_flagged_*.csv/.json         ← exceptional picks only
  options_opportunities_safest_*.csv/.json          ← top 10 safest
  options_opportunities_highest_yield_*.csv/.json   ← top 10 by yield
  options_opportunities_balanced_*.csv/.json        ← top 10 balanced
```

---

## Components

### Entry points

| File | Purpose |
|------|---------|
| `cli.py` | Unified CLI — `scan`, `watchlist`, `dashboard`, `serve`, `export` |
| `options_scanner.py` | Full-universe scanner class (`OptionsScanner`) |
| `dashboard.py` | Console/HTML dashboard renderer (runs scan + formats output) |

### Core library (`scanner/`)

| Module | Responsibility |
|--------|---------------|
| `indicators.py` | Black-Scholes Greeks for calls and puts |
| `option_chains.py` | yfinance option chain fetcher with file cache |
| `strategy_filters.py` | Screening rules + `scan_tickers()` pipeline |
| `alpaca_config.py` | Alpaca API credential loader (for future trade execution) |
| `backtest.py` | Back-testing harness over historical chain CSVs |

### Web dashboard (`web/`)

| File | Responsibility |
|------|---------------|
| `app.py` | Flask app — REST API + serves `index.html` |
| `results_loader.py` | Discovers and loads timestamped scan outputs |
| `templates/index.html` | Single-page dashboard UI |
| `static/css/dashboard.css` | Styling |
| `static/js/dashboard.js` | Client-side table rendering, sorting, filtering, Chart.js |

The web dashboard exposes:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Serve the SPA |
| `/api/scans` | GET | List all past scans (newest first) |
| `/api/results/latest` | GET | Full data payload for the latest scan |
| `/api/results/<timestamp>` | GET | Data for a specific past scan |
| `/api/scan` | POST | Trigger a new background scan |
| `/api/scan/status` | GET | Poll scan progress |

### Symbol lists (`symbol_lists/`)

| File | Content |
|------|---------|
| `sp500.json` | ~500 S&P 500 ticker symbols |
| `nasdaq100.json` | ~100 Nasdaq-100 ticker symbols |
| `watchlist.csv` | User-editable: `ticker, company_name, sector, weight` |
| `watchlist_parser.py` | Reads watchlist CSV into a dict |

---

## CLI Commands

```bash
# Scan the watchlist only (fast — 5 tickers)
python cli.py
python cli.py --debug

# Full universe scan (S&P 500 + Nasdaq-100 + watchlist, ~600 tickers — slow)
python cli.py scan

# Filter latest full scan results to one ticker
python cli.py scan --ticker AAPL

# Print path to latest output file
python cli.py export --format csv
python cli.py export --format json

# Scan + render console/HTML dashboard
python cli.py dashboard
python cli.py dashboard --html       # also writes outputs/dashboard.html

# Start the Flask web UI
python cli.py serve                  # http://127.0.0.1:5000
python cli.py serve --port 8080
python cli.py serve --debug
```

---

## Data Dictionary

Key columns in every output file:

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | str | Underlying stock ticker |
| `current_price` | float | Stock price at scan time |
| `strike` | float | Put strike price |
| `expiration` | date | Contract expiry date |
| `premium` | float | Mid-price (bid+ask)/2 per share |
| `bid` / `ask` | float | Market bid and ask |
| `delta` | float | B-S delta (negative for puts, −0.30 to −0.10) |
| `open_interest` | int | Open contracts (liquidity indicator) |
| `days_to_expiration` | int | Calendar days until expiry |
| `annualized_yield` | float | `(premium / strike) / years × 100` % |
| `risk_adjusted_yield` | float | `(premium / (strike − premium)) / years × 100` % |
| `distance_otm` | float | `(price − strike) / price × 100` % |
| `bid_ask_spread_pct` | float | `(ask − bid) / premium × 100` % |
| `flagged` | bool | True if meets all exceptional criteria |

---

## Back-testing

The `scanner/backtest.py` harness replays the scanner over historic option chain CSVs:

1. Place historic chain files in `historical_data/<ticker>_<YYYY-MM-DD>.csv`
2. Create `backtest_input.json`:
   ```json
   {
     "AAPL": [["2024-06-01", 181.20], ["2024-07-01", 190.50]],
     "MSFT": [["2024-06-01", 415.00]]
   }
   ```
3. Run: `python -m scanner.backtest`

Returns per-ticker counts of candidates and flagged opportunities across all dates.

---

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `APCA_API_KEY_ID` | — | Alpaca API key (optional — future trade execution) |
| `APCA_API_SECRET_KEY` | — | Alpaca secret key |
| `APCA_API_BASE_URL` | `https://paper-api.alpaca.markets` | Alpaca base URL |

Copy `.env.example` to `.env` and populate. The scanner works fully without Alpaca credentials — yfinance is used for all data today.

---

## Directory Layout

```
Trading/
├─ scanner/                    # core library package
│   ├─ __init__.py             # public API surface
│   ├─ indicators.py           # Black-Scholes Greeks
│   ├─ option_chains.py        # yfinance fetcher + daily cache
│   ├─ strategy_filters.py     # screening pipeline
│   ├─ alpaca_config.py        # Alpaca credential dataclass
│   └─ backtest.py             # historical replay harness
├─ web/                        # Flask web dashboard
│   ├─ app.py                  # REST API + SPA host
│   ├─ results_loader.py       # scan file discovery & loading
│   ├─ templates/index.html    # SPA with tabbed tables + chart
│   └─ static/                 # CSS + JS
├─ symbol_lists/               # equity universe definitions
│   ├─ watchlist.csv           # ← edit this with your tickers
│   ├─ sp500.json
│   ├─ nasdaq100.json
│   └─ watchlist_parser.py
├─ outputs/                    # timestamped scan results (gitignored)
├─ data/cache/                 # option chain cache (gitignored)
├─ logs/                       # scanner + dashboard logs (gitignored)
├─ docs/                       # planning documents
├─ cli.py                      # unified CLI entry point
├─ options_scanner.py          # OptionsScanner class
├─ dashboard.py                # console + HTML dashboard
├─ requirements.txt
├─ .env.example
└─ README.md
```

---

## Dependencies

```
yfinance     ≥ 0.2   Option chains and stock data
pandas       ≥ 2.0   DataFrame manipulation throughout
numpy        ≥ 1.24  Array operations in Greeks calculations
scipy        ≥ 1.10  Normal distribution CDF/PDF for Black-Scholes
requests     ≥ 2.28  HTTP for Wikipedia symbol-list fallbacks
alpaca-py    ≥ 0.20  Alpaca SDK (credential loading; trading not yet implemented)
rich         ≥ 13.0  Formatted console tables in dashboard
flask        ≥ 3.0   Web dashboard server
```

---

## Limitations and Known Gaps

- **Alpaca integration not implemented** — credentials are loaded but no order placement exists.
- **No real-time data** — yfinance data has a 15-minute delay during market hours.
- **Greeks from yfinance omitted** — yfinance rarely returns delta; the B-S calculator fills in all Greeks. Implied volatility is taken from yfinance and may differ from market-maker quotes.
- **Single expiration per ticker** — the scanner picks the furthest available expiry ≥ 12 months. It does not yet sweep multiple expirations.
- **Back-test requires manual data download** — `historical_data/` CSVs must be sourced and formatted externally.
- **No assignment/P&L simulation** — the back-tester counts opportunities but does not simulate outcomes (assignment, roll, buy-back).
- **No authentication on the web dashboard** — the Flask app should not be exposed publicly without adding auth.
