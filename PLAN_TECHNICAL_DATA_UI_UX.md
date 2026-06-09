# CSP Scanner — Pivot Points & Bollinger Bands Integration

## Context

Before selling any CSP, a professional options trader checks pivot points (1D/1W/1M) and Bollinger Bands to confirm the strike is well below support levels and the stock is in a trending/stable regime — not oversold or in breakdown. Currently the scanner has zero technical context: it ranks purely on yield, delta, and OI. This means a contract could show a 30% real yield, delta -0.15, OI 2,000 — and look perfect — while the stock is sitting on a broken monthly pivot with the BB lower band acting as the only floor. That trade is a trap.

The goal: compute pivot levels (1D/1W/1M) and Bollinger Bands (20-period, ±2σ) per ticker at scan time, attach them to every option row, surface them in the dashboard, and use them to generate a **Technical Context Score** — a composite signal that answers "is this a good time to sell a put on this stock?"

---

## The Professional Trading Logic

### Pivot Points (Standard / Floor Trader)
- Formula uses prior period's High/Low/Close:
  - `PP = (H + L + C) / 3`
  - `R1 = 2×PP − L`, `R2 = PP + (H − L)`, `R3 = H + 2×(PP − L)`
  - `S1 = 2×PP − H`, `S2 = PP − (H − L)`, `S3 = L − 2×(H − PP)`
- **1D pivot**: uses yesterday's candle — intraday S/R levels
- **1W pivot**: uses last week's candle — swing trade S/R
- **1M pivot**: uses last month's candle — positional S/R

### Bollinger Bands (20/2)
- `BB_middle = 20-period SMA of close`
- `BB_upper = middle + 2σ`, `BB_lower = middle − 2σ`
- `BB_width = (upper − lower) / middle × 100` — volatility regime indicator
- `BB_pct_b = (price − lower) / (upper − lower)` — where price is in the band (0=lower, 1=upper, 0.5=middle)

### Trading Signals (how pivot+BB improves CSP selection)

| Condition | Signal | Action |
|-----------|--------|--------|
| Strike < Weekly S2 | ✅ Strike is well below weekly support | Strong green — this is the target zone |
| Strike < Weekly S1 | ✅ Strike below first weekly support | Green — acceptable cushion |
| Strike > Weekly PP | ⛔ Strike is above weekly pivot | Red — far too risky, stock only needs to pull back to fair value |
| Price > Weekly PP | ✅ Stock trending above pivot | Green — stock has momentum on your side |
| Price < Daily PP | ⚠️ Stock below daily pivot | Amber — bearish intraday; wait for bounce |
| Price < Monthly PP | ⛔ Stock in monthly downtrend | Red — do not sell puts |
| BB %B < 0.2 | ⛔ Price near lower BB | Red — oversold, IV inflated by fear, gap risk high |
| BB %B > 0.8 | ⚠️ Price near upper BB | Amber — extended, mean-reversion risk |
| BB Width < 10% | ✅ Bands contracting | Green — low vol regime, stable trend, theta-friendly |
| BB Width > 30% | ⚠️ Bands wide/expanding | Amber — vol expansion, directional move likely |

### Technical Context Score (0–100)
Composite score from signal weights:
- Strike vs weekly S1/S2: 30 points
- Price vs weekly pivot: 25 points
- Price vs monthly pivot: 20 points
- BB %B position: 15 points
- BB width regime: 10 points

Score interpretation: ≥70 = ✅ Strong setup | 50–69 = ⚠️ Marginal | <50 = ⛔ Avoid

---

## Implementation Plan

### New file: `scanner/technicals.py`
Self-contained module. No external TA library needed — pure pandas/numpy. Per-ticker cache (dict keyed by symbol, refreshed at scan start):

```python
import yfinance as yf
import pandas as pd
from typing import Dict, Any

_tech_cache: Dict[str, Dict[str, Any]] = {}

def _pivot_from_candle(h: float, l: float, c: float) -> dict:
    pp = (h + l + c) / 3
    return {
        "pp": pp,
        "r1": 2*pp - l, "r2": pp + (h-l), "r3": h + 2*(pp-l),
        "s1": 2*pp - h, "s2": pp - (h-l), "s3": l - 2*(h-pp),
    }

def get_technicals(symbol: str, current_price: float) -> Dict[str, Any]:
    """
    Returns pivot levels and BB data for a symbol.
    Fetches daily OHLCV (60 days) — enough for 1D/1W/1M pivots and 20-day BB.
    Result is cached in _tech_cache for the duration of a scan run.
    """
    if symbol in _tech_cache:
        return _tech_cache[symbol]

    result = _empty_technicals()
    try:
        hist = yf.Ticker(symbol).history(period="60d", interval="1d")
        if len(hist) < 21:
            _tech_cache[symbol] = result
            return result

        # Daily pivot: previous trading day candle
        d = hist.iloc[-2]
        result["pivot_1d"] = _pivot_from_candle(d.High, d.Low, d.Close)

        # Weekly pivot: most recent complete week (resample to W)
        weekly = hist.resample("W-FRI").agg({"High":"max","Low":"min","Close":"last"})
        if len(weekly) >= 2:
            w = weekly.iloc[-2]
            result["pivot_1w"] = _pivot_from_candle(w.High, w.Low, w.Close)

        # Monthly pivot: most recent complete month
        monthly = hist.resample("ME").agg({"High":"max","Low":"min","Close":"last"})
        if len(monthly) >= 2:
            m = monthly.iloc[-2]
            result["pivot_1m"] = _pivot_from_candle(m.High, m.Low, m.Close)

        # Bollinger Bands (20/2) on daily closes
        closes = hist["Close"]
        sma20 = closes.rolling(20).mean().iloc[-1]
        std20 = closes.rolling(20).std().iloc[-1]
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20
        bb_width_pct = (bb_upper - bb_lower) / sma20 * 100 if sma20 > 0 else 0
        bb_pct_b = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

        result["bb_upper"]     = round(bb_upper, 2)
        result["bb_middle"]    = round(sma20, 2)
        result["bb_lower"]     = round(bb_lower, 2)
        result["bb_width_pct"] = round(bb_width_pct, 1)
        result["bb_pct_b"]     = round(bb_pct_b, 3)

    except Exception:
        pass

    _tech_cache[symbol] = result
    return result

def tech_score(technicals: dict, strike: float, current_price: float) -> int:
    """Compute 0-100 Technical Context Score for a specific strike."""
    score = 0
    w = technicals.get("pivot_1w", {})
    m = technicals.get("pivot_1m", {})
    d = technicals.get("pivot_1d", {})

    # Strike vs weekly S1/S2 (30 pts)
    if w:
        if strike < w.get("s2", 0):      score += 30
        elif strike < w.get("s1", 0):    score += 18
        elif strike < w.get("pp", 0):    score += 6

    # Price vs weekly pivot (25 pts)
    if w and w.get("pp"):
        if current_price > w["pp"]:      score += 25
        elif current_price > w["s1"]:    score += 10

    # Price vs monthly pivot (20 pts)
    if m and m.get("pp"):
        if current_price > m["pp"]:      score += 20
        elif current_price > m["s1"]:    score += 8

    # BB %B (15 pts) — penalise oversold/overbought
    pct_b = technicals.get("bb_pct_b", 0.5)
    if 0.3 <= pct_b <= 0.7:             score += 15
    elif 0.2 <= pct_b < 0.3:            score += 8
    elif pct_b > 0.7:                   score += 8

    # BB width (10 pts) — reward low-vol regime
    width = technicals.get("bb_width_pct", 20)
    if width < 10:                       score += 10
    elif width < 20:                     score += 6
    elif width < 30:                     score += 3

    return min(score, 100)

def reset_tech_cache():
    _tech_cache.clear()
```

### Changes to `options_scanner.py`

1. Import `get_technicals`, `tech_score`, `reset_tech_cache` from `scanner/technicals.py`
2. In `run_scan()` start: call `reset_tech_cache()` to clear stale data
3. In `scan_stock(symbol, current_price, ...)`: after fetching current price, call `get_technicals(symbol, current_price)` — one call per symbol, result cached for all its contracts
4. In the option row assembly loop: add tech fields to each row dict:
   ```python
   tech = get_technicals(symbol, current_price)
   t_score = tech_score(tech, strike, current_price)
   row.update({
       "tech_score":      t_score,
       "pivot_1d_pp":     tech.get("pivot_1d", {}).get("pp"),
       "pivot_1d_s1":     tech.get("pivot_1d", {}).get("s1"),
       "pivot_1d_r1":     tech.get("pivot_1d", {}).get("r1"),
       "pivot_1w_pp":     tech.get("pivot_1w", {}).get("pp"),
       "pivot_1w_s1":     tech.get("pivot_1w", {}).get("s1"),
       "pivot_1w_s2":     tech.get("pivot_1w", {}).get("s2"),
       "pivot_1w_r1":     tech.get("pivot_1w", {}).get("r1"),
       "pivot_1m_pp":     tech.get("pivot_1m", {}).get("pp"),
       "pivot_1m_s1":     tech.get("pivot_1m", {}).get("s1"),
       "pivot_1m_s2":     tech.get("pivot_1m", {}).get("s2"),
       "bb_upper":        tech.get("bb_upper"),
       "bb_middle":       tech.get("bb_middle"),
       "bb_lower":        tech.get("bb_lower"),
       "bb_width_pct":    tech.get("bb_width_pct"),
       "bb_pct_b":        tech.get("bb_pct_b"),
   })
   ```
5. Add all 16 new fields to `fieldnames` list

### Changes to `web/static/js/dashboard.js`

**Table columns** (added to extra cols, hidden by default, shown with ⊕ More):

```javascript
// In renderTable() template string, after existing extra cols:
<td class="col-extra${show}">
  <span class="tech-score tech-score--${techBand(r.tech_score)}">${r.tech_score ?? '—'}</span>
</td>
<td class="col-extra${show}">${r.pivot_1w_pp ? '$'+fmt2(r.pivot_1w_pp) : '—'}</td>
<td class="col-extra${show}">${r.pivot_1w_s1 ? '$'+fmt2(r.pivot_1w_s1) : '—'}</td>
<td class="col-extra${show}">${r.pivot_1w_s2 ? '$'+fmt2(r.pivot_1w_s2) : '—'}</td>
<td class="col-extra${show}">${r.pivot_1m_pp ? '$'+fmt2(r.pivot_1m_pp) : '—'}</td>
<td class="col-extra${show}">${r.pivot_1m_s1 ? '$'+fmt2(r.pivot_1m_s1) : '—'}</td>
<td class="col-extra${show}">${r.bb_upper ? '$'+fmt2(r.bb_upper) : '—'}</td>
<td class="col-extra${show}">${r.bb_middle ? '$'+fmt2(r.bb_middle) : '—'}</td>
<td class="col-extra${show}">${r.bb_lower ? '$'+fmt2(r.bb_lower) : '—'}</td>
<td class="col-extra${show}">${r.bb_pct_b != null ? fmt2(r.bb_pct_b*100)+'%' : '—'}</td>
<td class="col-extra${show}">${r.bb_width_pct != null ? fmt2(r.bb_width_pct)+'%' : '—'}</td>
```

**Helper function:**
```javascript
function techBand(score) {
  if (score == null) return 'na';
  if (score >= 70) return 'strong';
  if (score >= 50) return 'marginal';
  return 'weak';
}
```

**Tech score also shown in the banded picks cards** — adds one line to `renderBandedPicks`:
```javascript
<div class="band-row band-tech">
  <span>Tech Score</span>
  <strong class="tech-score tech-score--${techBand(r.tech_score)}">${r.tech_score ?? '—'}/100</strong>
</div>
```

### Changes to `web/templates/index.html`

Add column headers (in extra cols section):
```html
<th data-sort="tech_score" class="col-extra hidden">
  Tech Score
  <span class="col-info" data-tip="0–100 composite signal: strike vs weekly/monthly pivots, price vs pivots, Bollinger Band position. ≥70 = strong setup, 50–69 = marginal, <50 = avoid.">ⓘ</span>
</th>
<th class="col-extra hidden">W.PP <span class="col-info" data-tip="Weekly Pivot Point — the key level. Price above = bullish, below = bearish for the week.">ⓘ</span></th>
<th class="col-extra hidden">W.S1 <span class="col-info" data-tip="Weekly Support 1 — first support. Strike below this = good cushion.">ⓘ</span></th>
<th class="col-extra hidden">W.S2 <span class="col-info" data-tip="Weekly Support 2 — deep support. Strike below this = very strong positioning.">ⓘ</span></th>
<th class="col-extra hidden">M.PP <span class="col-info" data-tip="Monthly Pivot Point — positional support/resistance. Price above = monthly uptrend.">ⓘ</span></th>
<th class="col-extra hidden">M.S1 <span class="col-info" data-tip="Monthly Support 1 — major support level. Best CSP strikes are below M.S1.">ⓘ</span></th>
<th class="col-extra hidden">BB Upper <span class="col-info" data-tip="Bollinger Band upper band (20-day SMA + 2σ). Price near here = extended, mean-reversion risk.">ⓘ</span></th>
<th class="col-extra hidden">BB Mid <span class="col-info" data-tip="Bollinger Band middle (20-day SMA). Price above = bullish trend, below = bearish.">ⓘ</span></th>
<th class="col-extra hidden">BB Lower <span class="col-info" data-tip="Bollinger Band lower band (20-day SMA − 2σ). Strike ideally below this level.">ⓘ</span></th>
<th class="col-extra hidden">BB %B <span class="col-info" data-tip="Where price sits in the Bollinger Band (0%=lower band, 100%=upper band). 20–80% is the safe zone for CSP selling.">ⓘ</span></th>
<th class="col-extra hidden">BB Width <span class="col-info" data-tip="Band width as % of mid-price. Under 10% = volatility squeeze = stable regime. Over 30% = vol expansion = directional move coming.">ⓘ</span></th>
```

### Changes to `web/static/css/dashboard.css`

```css
/* Tech Score badge */
.tech-score { font-weight: 700; padding: .1rem .35rem; border-radius: 4px; font-size: .78rem; }
.tech-score--strong   { background: var(--green-dim); color: var(--green); }
.tech-score--marginal { background: var(--amber-dim); color: var(--amber); }
.tech-score--weak     { background: var(--red-dim);   color: var(--red);   }
.tech-score--na       { color: var(--text-3); }
```

---

## Performance Note

The `get_technicals()` call fetches 60 days of daily bars per symbol — **one extra yfinance call per ticker** (not per contract). With ~114 symbols in a typical scan:
- 114 extra API calls × ~0.3s avg = ~35 seconds additional scan time
- Result is cached per scan run — contracts for the same ticker reuse the same data
- This is acceptable; the existing scan already takes 60–120 seconds

---

## Files to Modify

| File | Change |
|------|--------|
| `scanner/technicals.py` | **NEW** — pivot calc, BB calc, tech_score(), cache |
| `options_scanner.py` | Import technicals, call get_technicals() in scan_stock(), add 16 fields to fieldnames |
| `web/templates/index.html` | 11 new `<th>` headers in extra cols section; bump to `?v=16` |
| `web/static/js/dashboard.js` | 11 new `<td>` in renderTable(), techBand() helper, tech score in banded picks cards; update extraCols list |
| `web/static/css/dashboard.css` | Tech score badge styles |

---

## Verification

1. Run `python3 -c "from scanner.technicals import get_technicals, tech_score; t=get_technicals('AAPL', 210); print(t); print(tech_score(t, 190, 210))"` — confirm pivot + BB values print
2. Run a short scan (watchlist of 3–5 symbols) — confirm new fields appear in `outputs/*.json`
3. Open `http://127.0.0.1:5001` → click ⊕ More columns → confirm Tech Score, pivot, and BB columns appear
4. Verify Tech Score badge colors: green ≥70, amber 50–69, red <50
5. In banded picks cards, confirm Tech Score line renders for each band
6. Check scan duration — confirm <3 minutes total for full run

---

# CSP Scanner — Alpaca Paper Account Integration

## Context

The user has been manually executing trades in an Alpaca paper account based on scanner results. The goal is to close the loop: connect the dashboard to Alpaca paper trading so the user can see account health, track open positions, view order history, and submit CSP orders directly from scanner rows — all without leaving the dashboard.

`alpaca-py>=0.20.0` is already in `requirements.txt`. A credential loader (`scanner/alpaca_config.py`) already exists. Credentials will be stored in `localStorage` (never persisted server-side) and passed per-request via custom headers.

---

## What We're Building

### 1 — Settings Drawer (credential entry)
A ⚙️ button in the topbar opens a settings modal where the user pastes their Alpaca paper API key + secret. Stored in `localStorage`. On save, immediately fetches account data.

Backend routes accept credentials in request headers (`X-APCA-Key`, `X-APCA-Secret`) — server never stores them.

### 2 — Account Panel (new zone between Step 1 and chart)
Compact horizontal card:
```
[ $24,831 Cash ]  [ $18,200 Buying Power ]  [ 3 Positions ]  [ 1 Pending Order ]
                  Paper Account · alpaca.markets    [↻ Refresh]
```
Shows "Connect Alpaca →" placeholder when no credentials saved.

### 3 — Positions Tab
New **"📋 Positions"** tab in the existing tab bar. Shows open positions from Alpaca `/v2/positions`:

| Symbol | Qty | Avg Cost | Current | P&L | P&L % |

### 4 — Orders Tab
New **"📜 Orders"** tab showing last 20 orders from Alpaca `/v2/orders`:

| Symbol | Side | Qty | Type | Status | Filled At | Fill Price |

### 5 — One-Click "Sell Put" Button
Each scanner row gets a **[Sell Put]** button (visible only when Alpaca connected). Opens a **trade review modal**:
```
SELL 1 × AAPL 280P Aug 15 2026
Type: Limit · Price: $2.50 (mid-price)
Capital Required: $28,000
Real Yield: 15.6% · Delta: -0.14
[Cancel]   [✓ Submit to Alpaca]
```
On confirm → `POST /api/alpaca/order` → green banner + positions refresh.

---

## Implementation Plan

### New file: `web/alpaca_service.py`
Thin wrapper; all functions take `(key, secret)` as params — no env var dependency:
```python
from alpaca.trading.client import TradingClient
def get_client(key, secret): return TradingClient(key, secret, paper=True)
def get_account(key, secret) -> dict        # cash, buying_power, equity
def get_positions(key, secret) -> list      # open positions
def get_orders(key, secret, limit=20) -> list
def place_csp_order(key, secret, symbol, expiry, strike, limit_price, qty=1) -> dict
```

### New routes in `web/app.py`
```
GET  /api/alpaca/account    → account balance + buying power
GET  /api/alpaca/positions  → open positions list
GET  /api/alpaca/orders     → recent orders (last 20)
POST /api/alpaca/order      → submit CSP limit order
     body: { symbol, expiration, strike, limit_price, qty }
```
All extract `X-APCA-Key` / `X-APCA-Secret` from headers. Return `{"error": "..."}` on failure.

### `web/templates/index.html`
1. ⚙️ Settings button in topbar (before History button)
2. Settings modal: two password inputs (key/secret) + Save/Clear buttons
3. Account panel zone after `setup-card`
4. "📋 Positions" and "📜 Orders" tab buttons in existing tab bar
5. [Sell Put] column in table `<thead>` and rows (hidden via CSS class when not connected)
6. Trade review modal overlay
7. Bump to `?v=15`

### `web/static/js/dashboard.js`
```javascript
// Credentials
function alpacaHeaders() { return { 'X-APCA-Key': localStorage.getItem('alpaca_key'), 'X-APCA-Secret': localStorage.getItem('alpaca_secret') }; }
function isAlpacaConnected() { return !!(localStorage.getItem('alpaca_key')); }

// Account panel
async function loadAlpacaAccount() { ... }  // fetch /api/alpaca/account, render KPIs

// Tab handling: add cases "positions" and "orders" in tabFilter()
// These fetch from Alpaca and render with a different column schema

// Trade modal
function openTradeModal(row) { /* populate and show modal */ }
async function submitOrder() { /* POST /api/alpaca/order, show banner, refresh */ }
```

### `web/static/css/dashboard.css`
- `.alpaca-panel` — account card (reuse surface/border CSS vars)
- `.alpaca-kpi` — inline chips inside account panel
- `.modal-overlay`, `.modal-card` — trade review + settings modals
- `.btn-sell-put` — compact amber button in table
- `.account-placeholder` — "Connect Alpaca →" state

---

## Files to Modify

| File | Change |
|------|--------|
| `web/alpaca_service.py` | **NEW** — Alpaca SDK wrapper |
| `web/app.py` | Add 4 new `/api/alpaca/*` routes |
| `web/templates/index.html` | Settings modal, account panel, Positions/Orders tabs, Sell Put column, trade modal; `?v=15` |
| `web/static/js/dashboard.js` | Credential mgmt, account panel, new tab cases, trade modal logic |
| `web/static/css/dashboard.css` | Modal + account panel + sell-put button styles |

---

## Verification

1. Open `http://127.0.0.1:5001` — ⚙️ button visible in topbar
2. Click ⚙️ → enter Alpaca paper key/secret → Save → account panel populates
3. Account panel shows cash, buying power, position count, pending orders
4. "📋 Positions" tab → open positions table from Alpaca
5. "📜 Orders" tab → recent order history
6. [Sell Put] button visible on each scanner row
7. Click [Sell Put] → modal shows correct symbol, strike, expiry, mid-price
8. Confirm → green banner "Order submitted", positions refresh
9. Cancel → modal closes, no order placed
10. Clear credentials → panel reverts to placeholder

---

# CSP Scanner — Full UAT Bug Report

## UAT Audit Summary

Full audit across backend, frontend, and data quality. Total: **19 bugs found** — 5 Critical, 7 High, 5 Medium, 2 Low.

---

## 🔴 CRITICAL (broken / shows wrong data to trader)

### C1 — "Safest" tab/section sorts in WRONG direction
**File:** `web/results_loader.py` lines 101–104  
`ascending=[False, True, False]` on raw `delta` (negative numbers). Ascending on negatives means -0.30 comes before -0.10, so the **riskiest contract shows first**, not the safest.  
**Fix:** Add an absolute-value column: `df_all['abs_delta'] = df_all['delta'].abs()` and sort by that ascending.

### C2 — Same wrong sort in backend scanner's safest section
**File:** `options_scanner.py` (generate_summary_sections)  
Confirmed same pattern: sorts by raw delta ascending instead of abs(delta) ascending.  
**Fix:** Same approach — use abs() for the sort key, not raw delta.

### C3 — Empty-state table colspan is wrong when extra columns shown
**File:** `web/static/js/dashboard.js` line 314  
Empty row uses `colspan="${COLS}"` where `COLS = colsExpanded ? 15 : 9`. But the actual thead always has 15 columns (6 are hidden via CSS, not removed from DOM). This misaligns the empty row width.  
**Fix:** Always use `colspan="15"` for the empty state cell.

### C4 — Best Pick card doesn't hide when its contract no longer passes account-size filter
**File:** `web/static/js/dashboard.js` line 279  
`renderBestPick(rows)` is passed `tabRows` (already filtered), so if the best pick's capital exceeds account size it's already gone from `rows`. **BUT** `renderBestPick` re-runs `balancedScore` on `rows` and picks #1 — so it correctly won't show an unaffordable contract. **However**: the capital highlight class (line 289) uses `account * 0.2` as the threshold, which means it only turns amber if capital > 20% of account. A contract at exactly 100% of account ($30k for $30k account) won't turn amber. This is misleading.  
**Fix:** Change threshold to `capital_required > account` (not 0.2 × account) for the amber highlight.

### C5 — KPI "High Yield" count and "⚡ High Yield" tab count diverge when filters active
**File:** `web/static/js/dashboard.js` line ~188  
`updateKPIs()` counts flagged rows from `allRows` (the full dataset). The ⚡ tab filters from `filteredRows`. So KPI shows "8 High Yield" but the tab shows 3 rows — confusing for a trader.  
**Fix:** Either update KPIs from `filteredRows` as well, or add a note "(X of Y)" to the tab.

---

## 🟠 HIGH (materially wrong behaviour)

### H1 — Chart ignores account size filter
**File:** `web/static/js/dashboard.js` `updateChart()` ~line 370  
Chart's Top 10 comes from `allRows` with OI≥500. It does NOT apply the account size filter. A user with $10k sees expensive contracts ($30k+) in the chart that are hidden from the table. Contradictory UX.  
**Fix:** Apply account filter inside `updateChart()` the same way `applyFilters()` does.

### H2 — Chart doesn't clear stale data when no eligible rows
**File:** `web/static/js/dashboard.js` `updateChart()` line 376  
`if (!eligible.length) return;` — exits early without destroying the old chart. Old chart data stays on screen.  
**Fix:** Destroy `chartInstance` before returning early on empty.

### H3 — "Safest" tab loses OI ordering (double-sort bug)
**File:** `web/static/js/dashboard.js` lines 239–240  
Takes top 50 by OI then re-sorts by abs(delta). The second sort discards OI ranking entirely.  
**Fix:** Sort by a combined score: primarily OI descending, secondarily delta ascending, in one pass.

### H4 — Custom DTE fields not pre-filled when user first clicks "Custom"
**File:** `web/static/js/dashboard.js` `setPreset()`  
When user switches from STANDARD (38–52) to CUSTOM, the inputs still show 1 and 730 (HTML defaults). The user doesn't see the current preset's values as a starting point.  
**Fix:** In `setPreset("CUSTOM")`, copy the previously active preset's min/max into the custom inputs.

### H5 — Scan history dropdown shows "Loading…" forever on fetch error
**File:** `web/static/js/dashboard.js` `loadScanHistory()` ~line 168  
Catch block is empty — doesn't update the select element. "Loading…" persists indefinitely.  
**Fix:** On catch, set innerHTML to `<option value="">Error loading history</option>`.

### H6 — Sort indicator (↑↓) on column headers not cleared when switching tabs
**File:** `web/static/js/dashboard.js` `initTableSort()`  
User sorts "Real Yield ↓", switches to "Safest" tab (which overrides sorting internally), but the ↓ arrow stays on Real Yield header. Header lies about what order the data is in.  
**Fix:** Clear all sort classes on tab switch, or re-apply user's sort inside each tab.

### H7 — Timezone inconsistency in DTE calculations (non-UTC systems)
**File:** `indicators.py` uses `datetime.utcnow()`, `options_scanner.py` uses `datetime.now()` (local)  
On US/Eastern systems (UTC-4), DTE boundary decisions differ by 4+ hours between modules. Contracts at the DTE edge may be accepted or rejected inconsistently.  
**Fix:** Standardise on `datetime.utcnow()` across all three files (`indicators.py`, `options_scanner.py`).

---

## 🟡 MEDIUM (wrong display / confusing UX)

### M1 — Tooltip can overflow top/left edge of viewport
**File:** `web/static/js/dashboard.js` `initTooltips()` lines 459–460  
Only checks right and bottom overflow. Near top-left of screen the tooltip goes off-viewport.  
**Fix:** Add `if (x < 8) x = e.clientX + 14;` and `if (y < 8) y = e.clientY + 14;`

### M2 — Earnings warning "⚠" text missing "0d" when days_to_earnings = 0
**File:** `web/static/js/dashboard.js` line 323  
`r.days_to_earnings ? " " + r.days_to_earnings + "d" : ""` — falsy check on 0 suppresses the text. Earnings today shows "⚠" with no days label.  
**Fix:** `r.days_to_earnings != null ? ...` instead of truthy check.

### M3 — Sort state on hidden columns confuses users
**File:** `web/static/js/dashboard.js`  
When extra columns are visible and user sorts by IV%, then collapses columns, the IV header is hidden but was still the active sort. The "↑" arrow disappears visually but the sort is still applied — invisible state.  
**Fix:** Reset sort to `realistic_yield desc` whenever user collapses extra columns.

### M4 — No way to clear account size (stuck filter)
**File:** `web/templates/index.html` — `#account-size-input` has `min="1000"`  
Once set, user must manually delete and blur to clear. Input HTML min prevents entering 0. No X/clear affordance.  
**Fix:** Remove `min="1000"` from HTML; JS already handles `|| 0` gracefully. Add placeholder "Leave blank = no limit."

### M5 — Highest Yield tab sorts by `risk_adjusted_yield` but displayed column is `realistic_yield`
**File:** `web/static/js/dashboard.js` line 242  
`tabFilter "highest_yield"` sorts by `risk_adjusted_yield`. But the primary column shown is "Real Yield %" (`realistic_yield`). They are different numbers (realistic = risk_adj × (1+delta)). The sort column doesn't match what the trader sees highlighted.  
**Fix:** Sort "Highest Yield" tab by `realistic_yield` to match the visible column.

---

## ⚪ LOW (minor polish)

### L1 — `aria-pressed` missing on column toggle button
**File:** `web/templates/index.html` line ~222  
`<button id="cols-toggle">` has no `aria-pressed` attribute. Screen readers can't tell if extra columns are expanded.  
**Fix:** Add `aria-pressed="false"` and toggle it in JS alongside the `.active` class.

### L2 — `strategy_filters.py` is dead code with a different (wrong) premium formula
**File:** `scanner/strategy_filters.py`  
Never imported anywhere. Uses `row['bid'] * 100` instead of midpoint `(bid+ask)/2 * 100`. Risk of confusion if someone reads it and thinks it's authoritative.  
**Fix:** Delete the file or add a clear `# DEPRECATED` comment at the top.

---

## Data Quality (from output audit)
The actual scan JSON output is **financially accurate** — all formulas verified correct:
- `capital_required = strike × 100` ✓
- `realistic_yield = risk_adjusted_yield × (1 + delta)` ✓
- `premium = (bid + ask) / 2` ✓
- `bid_ask_spread_pct = (ask - bid) / premium × 100` ✓
- All strikes are OTM ✓, delta in −0.30 to −0.10 ✓, OI filter working ✓
- One note: IV is stored as percentage (37.9) not decimal (0.379) — consistent but non-standard.

---

# CSP Scanner — Scan Architecture Fix + UX Optimization

## Context

**The user's question**: "When I click Run Scan, it scans ALL data but the sidebar filters just filter client-side — is that right? Will it work well?"

**The honest CTO answer**: The current architecture is *partially correct* but has three problems:

1. **The scan is broken right now** — the API returns `data.all` but the JS reads `data.results`. This is why the last scan "did not work properly" — the dashboard shows zero rows despite a successful scan.
2. **The architecture is correct in principle** — scan everything once, filter client-side. This is exactly how Robinhood, Bloomberg, and every high-performance financial dashboard works. Re-running a 580-stock scan every time a filter changes would be unusable (takes 60–120 seconds).
3. **There is one legitimate UX gap** — the DTE preset in Step 1 controls what the *backend scans*, but the DTE filter in the sidebar only filters the *already-loaded results*. This is confusing: if you scanned 38–52 DTE and then set the sidebar DTE filter to 1–30, you get zero results with no explanation why.

**What to fix**:
- Bug: `data.all` → `data.results` key mismatch (dashboard shows nothing after scan)
- Bug: `data.summary.scan_time` not surfaced at top level (timestamps blank)
- UX: Sidebar DTE filter should be pre-populated from the scan's DTE window (not 1–730)
- UX: Label the two layers clearly so users understand Step 1 = "what to fetch" vs sidebar = "refine what was fetched"

---

## Architecture Decision (keep, don't change)

**Scan backend** enforces: DTE window, delta (−0.10 to −0.30), OI ≥ 100, volume ≥ 1M, bid-ask ≤ 10%, OTM strike. Returns ~200 rows for the full S&P 500 + Nasdaq 100 universe.

**Client-side filters** let the user *refine* those ~200 rows instantly: by ticker, min yield, max delta, tighter DTE sub-window, high-yield only, account size. No network call.

This is the right architecture. The fix is to make it bug-free and transparent to the user.

---

## Fix 1 — Critical: API response key mismatch (why last scan showed nothing)

**File**: `web/results_loader.py` lines 175–190

The `load_scan()` function returns `"all": all_records` but `dashboard.js` reads `data.results`. Simple rename + add `scan_time` at top level:

```python
return {
    "timestamp": timestamp,
    "scan_time": scan_meta["scan_time"],   # ADD — JS expects this at top level
    "summary": { ... },
    "results": all_records,               # WAS "all"
    "flagged": flagged,
    ...
}
```

No JS changes needed — dashboard.js already reads `data.results` and `data.scan_time` correctly.

---

## Fix 2 — Pre-populate sidebar DTE from scan window

When results load, set sidebar DTE inputs to match what was scanned so the user doesn't accidentally filter to a range outside the scan window.

**File**: `web/static/js/dashboard.js` — in `loadLatestResults()` after `allRows = data.results`:
```javascript
const dMin = data.summary?.dte_min || 1;
const dMax = data.summary?.dte_max || 730;
$("filter-dte-min").value = dMin;
$("filter-dte-max").value = dMax;
```

Also apply the same in `loadScanByTimestamp()`.

---

## Fix 3 — UX clarity labels

**File**: `web/templates/index.html`

- STEP 1 card: add a subtitle line under the label: *"Sets what the scanner fetches across 580 stocks"*
- Sidebar heading: change `FILTER RESULTS` → `REFINE RESULTS`
- Add one-line hint below sidebar heading: *"Instant filter on loaded data — no re-scan needed"*
- Update sidebar DTE `data-tip`: *"Narrows within the scan window. To change the DTE range entirely, update the preset in Step 1 and re-scan."*

---

## Fix 4 — Custom DTE validation

**File**: `web/static/js/dashboard.js` — in `startScan()`:
```javascript
if (min > max) { showError("Min DTE must be less than Max DTE."); return; }
```

---

## Files to Modify

| File | Change |
|------|--------|
| `web/results_loader.py` | Rename `"all"` → `"results"`, add top-level `"scan_time"` |
| `web/static/js/dashboard.js` | Pre-populate sidebar DTE from scan data; add DTE validation in startScan() |
| `web/templates/index.html` | Step 1 subtitle, sidebar "REFINE RESULTS" + hint line, updated DTE tooltip |

---

## Verification
1. `python3 cli.py serve --port 5001` → open `http://127.0.0.1:5001`
2. Click ▶ Run Scan (45-Day) → table should populate (was showing 0 rows before)
3. Confirm "Last scan: …" timestamp appears in Step 1 and KPI row
4. Confirm sidebar DTE auto-sets to 38–52 after scan loads
5. Select Custom DTE, set min=50 max=30 → confirm inline error appears, scan blocked
6. Confirm sidebar heading reads "REFINE RESULTS" with hint subtitle

---

# CSP Scanner — UI/UX Redesign Plan

## Context

Designed for a **laptop (13–15 inch)** screen. The target feeling is **"powerful but approachable"** — like a modern fintech app with rich data but clear visual hierarchy. The #1 pain is the **scan workflow is unclear** — users don't know what to do first. The redesign fixes this with a guided step-by-step flow, cleaner visual zones, and a table that surfaces the best trade at a glance.

---

## Design Principles (from Robinhood / modern fintech)

1. **One primary action per zone** — each section has one job. No competing buttons.
2. **Guide the eye top-to-bottom** — Step 1 (configure) → Step 2 (results) → Step 3 (pick a trade).
3. **Progressive disclosure** — show summary first, detail on demand. Don't dump 15 columns on load.
4. **Color means something** — green = good/safe, amber = caution, red = risk. Never decorative.
5. **Whitespace is not waste** — breathing room between zones reduces cognitive load.

---

## Zone-by-Zone Redesign

### Zone 1 — Top Bar (unchanged structure, visual polish only)
- Left: `CSP Scanner` brand + `research only · no trades placed` subtitle
- Right: scan history dropdown + `▶ Run Scan` button
- Change: make the toolbar slightly taller (56px), brand name larger, add a thin colored bottom border to separate from content below
- Remove: the current cramped feel — add more padding

### Zone 2 — Scan Setup (complete rethink — this fixes the #1 pain)

**Current problem**: DTE presets, Account $ input, and badge are all in one flat bar with no visual guide. User doesn't know this is "Step 1".

**New design — Guided Setup Strip**:
```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1 · CONFIGURE YOUR SCAN                                   │
│                                                                 │
│  Strategy DTE    [Weekly] [Monthly] [45-Day ✓] [Quarterly] [LEAPS] [Custom]
│                                                                 │
│  My Account Size  [$______]   ← filters out trades you can't afford
│                                                                 │
│  [▶ Run Scan]   Last scan: 2026-06-07 19:35                     │
└─────────────────────────────────────────────────────────────────┘
```
- Wrap the entire setup in a **card with a subtle left border accent** (blue) and a `STEP 1` label
- Move the `▶ Run Scan` button INTO this card — makes it obvious this is the action
- Account size gets a helper text: "We'll hide contracts that require more cash than this"
- The scan history dropdown moves to a small `📋 History` link in the top-right, not a dropdown taking up prime space

### Zone 3 — Scan Status Banner
- When scanning: full-width animated progress bar (not just a spinner) showing `Scanning AAPL… 47/550 stocks`
- When complete: a brief green flash "✓ Scan complete — 564 opportunities found" that auto-dismisses after 3s
- When error: red banner stays until dismissed

### Zone 4 — Summary Cards (visual redesign)

**Current problem**: 5 small KPI cards in a 2-column grid feel cluttered. The chart is squeezed.

**New design**:
- Reduce to **4 KPI cards** in a single horizontal row: Opportunities | High Yield | Symbols | Scan DTE
- Each card is wider and shorter (pill-style, 1 row)
- Remove "Scan Time" as a card — move it to a small timestamp line under the cards
- Chart takes **full width below** the cards (not side-by-side) — gives it room to breathe and be readable
- Chart height increases from ~160px to 220px

Layout:
```
[ 564 Opportunities ]  [ 34 High Yield ]  [ 5 Symbols ]  [ 38–52 DTE ]
                      Scanned 2026-06-07 19:35

[═══════════════ Top 10 Best Balanced Opportunities Chart ═══════════════]
```

### Zone 5 — Results (complete rethink — this is the core trader workflow)

**Current problem**: tabs + filters + row count are all jammed together. 15 columns make the table overwhelming.

**New design — Two-panel layout**:

#### Left panel: Filter sidebar (160px wide, always visible)
```
FILTER RESULTS
──────────────
Ticker  [_____]

Min Yield
[===] 0%

Max |Delta|
[===] 0.35

DTE Range
[__] – [__]

☐ High Yield only
```
Moving filters to a sidebar makes the table wider and removes the cluttered filter row above the table.

#### Right panel: Tabbed results
- Tabs stay: All | High Yield | Safest | Highest Yield | Balanced
- Add a **STEP 2** label above: `STEP 2 · PICK YOUR TRADE`
- Row count + filter summary move to a line ABOVE the table, not inside the results bar

#### Table redesign — "Best Trade" card on top
- Above the table, show a **"Best Pick" highlight card** — the #1 Balanced result as a visual card:
```
┌─────────────────────────────────────────────────── ⭐ Best Balanced Pick ──┐
│  AAPL   $307 →  Strike $280   Expiry Aug 15 (43d)                         │
│  Premium $2.50 · Yield 18.4% · Real Yield 15.6% · Capital $28,000        │
│  Delta −0.14 · IV 31% · θ $4.20/day · OI 1,243                          │
└────────────────────────────────────────────────────────────────────────────┘
```
- Clicking the card selects that row in the table

#### Table column reduction — from 15 to 9 visible columns
Too many columns = paralysis. Move less-critical columns behind a "⊕ More" toggle:

**Always visible (9 columns)**:
| Symbol | Price | Strike | Expiry (DTE) | Premium | Delta | Real Yield % | Capital | Flag |

**Hidden by default, shown on "⊕ More"**:
IV%, θ/day, OI, OTM%, Risk-Adj Yield%, Spread%

This way the trader sees the most decision-relevant columns first, and can expand if they want detail.

### Zone 6 — Contextual Help (Salesforce-style inline hints — apply everywhere)

Every metric that a new trader might not understand gets a `ⓘ` icon that shows a **"why it matters"** tooltip on hover — not just a definition, but *why you should care about it as a trader*. This applies to:

**Table column headers** (already partially done — upgrade the copy):
- `IV %` → *"Why IV matters: High IV = the market is scared = you collect fatter premium. Sell when IV is high, avoid when IV is low. Without checking IV, you're flying blind on whether this premium is actually worth taking."*
- `Real Yield %` → *"Why Real Yield matters: The raw Risk-Adj Yield assumes you win 100% of the time. Real Yield adjusts for the probability of expiring worthless. This is the number that actually matters for your expected income."*
- `Capital` → *"Why Capital matters: This cash gets locked in your account the moment you sell the put. A $30,000 capital requirement on a $10,000 account is impossible — your broker will reject the trade."*
- `Delta` → *"Why Delta matters: It tells you how likely you are to be assigned. −0.15 means 85% chance you keep the premium and walk away. −0.30 means 30% chance you end up owning the stock."*
- `θ/day` → *"Why Theta matters: This is your daily paycheck from time decay alone. A $4/day theta means you earn $4 every day the market is open, even if the stock doesn't move."*
- `OI` → *"Why OI matters: Low open interest = illiquid contract = wide bid-ask spread = you fill at a worse price. Always prefer OI above 500 to ensure you can enter and exit cleanly."*

**KPI cards** — each card gets a `ⓘ` icon:
- `High Yield` card → *"These 34 contracts meet all 4 exceptional criteria: yield >10%, OTM >15%, delta >−0.20, OI ≥500. WARNING: this combination usually only appears when IV is extremely elevated — verify IV before trading."*
- `Scan DTE` card → *"The DTE window this scan used. The 45-day range is the theta sweet spot — decay accelerates fastest between 30–45 days, giving you the best income-to-risk ratio."*

**Best Pick card** — small `ⓘ` in the corner:
- *"This is the #1 contract ranked by Balanced Score: 40% yield + 30% liquidity (OI) + 30% safety (low delta). It is not necessarily the highest yield — it is the best all-around trade."*

**Filter labels in the sidebar**:
- `Min Yield` → *"Filters out low-income contracts. 5%+ annualized is a reasonable starting floor for CSP selling."*
- `Max |Delta|` → *"Filters out high-risk contracts. Keep below 0.30 to stay in the 70%+ probability-of-profit zone."*
- `DTE Range` → *"Days to expiration. 38–52 days is the sweet spot for theta decay. Shorter = faster income but more gamma risk."*

**Implementation**: The existing JS `initTooltips()` function and `.col-info` CSS class already handle this. We just need to add `ⓘ` spans with `data-tip` attributes to KPI cards, filter labels, and the Best Pick card — reusing the exact same tooltip mechanism already built.

### Zone 7 — Guide / Help (visual polish)
- Keep the `?` FAB button and bottom drawer
- Add a small `New to CSP selling? Start here →` link next to the brand subtitle in the toolbar that opens the guide
- This makes the guide discoverable without being intrusive

---

## Color & Typography Changes

### Colors
- Background: keep `#0f1419` (dark navy — good)
- Surface: lighten slightly to `#16202e` — current `#1a2332` is a bit too dark on laptop screens
- Accent: keep `#3b82f6` (blue)
- **New**: add a `--gold: #f0b429` for the "Best Pick" card border — distinguishes it from regular accent
- Green/amber/red semantic colors: keep as-is (they work)

### Typography
- Increase base font from `14px` to `15px` — easier to read on 13-inch screens
- Table font stays `13px` (data density)
- Column headers: increase letter-spacing slightly for readability
- KPI values: bump from `1.9rem` to `2.2rem` — these are the hero numbers

### Spacing
- Add `8px` more padding inside cards
- Increase gap between zones from `1rem` to `1.25rem`
- Table row height: increase from current ~36px to 40px — less cramped

---

## Files to Modify

| File | Change |
|------|--------|
| `web/templates/index.html` | Full restructure: guided setup strip, sidebar filters, best pick card, column toggle |
| `web/static/css/dashboard.css` | New layout: sidebar + content split, best pick card styles, updated tokens, larger typography |
| `web/static/js/dashboard.js` | Best pick card render, column toggle (show/hide), sidebar filter wiring, updated KPI layout |

---

## What Does NOT Change
- All data fields stay the same (no backend changes)
- All existing functionality (scan, filters, sort, tabs, guide drawer) stays
- Dark theme stays
- Chart stays (just gets more vertical space)

---

## Verification
1. Open `http://127.0.0.1:5001` — confirm guided Step 1 / Step 2 labels visible
2. Confirm table shows 9 columns by default, "⊕ More" expands to 15
3. Confirm Best Pick card shows #1 Balanced row at top of results
4. Confirm filter sidebar is always visible and functional
5. Confirm KPI cards are in a single horizontal row
6. Resize browser to 1280px width — confirm layout doesn't break

# CSP Scanner — Trader Assessment & Recommendations

## Context

This evaluation is from the perspective of a seasoned wheel strategy trader assessing the platform
for an **average trader with low capital** (~$5K–$25K account). The goal is to identify what is
broken, what is misleading, what is missing, and what concrete improvements would make this
platform genuinely useful rather than just a pretty spreadsheet generator.

---

## Honest Assessment: What's Actually Wrong Today

### 🔴 Critical Problems (would cause a new trader to lose money or make bad decisions)

**1. The flagging criteria are backwards for low-capital traders**
- "Flagged" requires OTM > 15% AND yield > 10% AND OI > 500
- A put that is 15% OTM with 10%+ annualized yield sounds amazing — but for most liquid large-caps
  at 45 DTE, this combination almost never exists legitimately. When it does, it's because IV is
  extremely elevated (earnings, binary event, sector crisis), meaning the market is pricing in
  catastrophic downside. A beginner will see "★ Flagged" and think it's a safe high-income trade.
  It is the opposite — it's a high-risk trade dressed up as a recommendation.
- **Fix**: Rename "Flagged" to "High Risk / High Yield". Add a warning label. Add IV Rank context.

**2. Risk-free rate is hardcoded at 2.54% — it's wrong**
- `scanner/indicators.py` line 85: `risk_free_rate: float = 0.0254`
- Current Fed Funds rate is ~5.25–5.5% (2024–2025). This causes the scanner to **understate delta**
  (less negative than reality) for OTM puts, making contracts appear safer than they are.
- A -0.15 delta calculated at 2.54% RFR might be -0.18 at the correct rate. That's the difference
  between "this will expire worthless 85% of the time" and "this will expire worthless 82% of the time."
- **Fix**: Dynamically fetch 13-week T-bill rate from yfinance (`^IRX`) at scan time.

**3. No earnings calendar warning**
- The scanner happily shows a NVDA put expiring in 8 days when NVDA reports earnings in 3 days.
  Selling a CSP before earnings is extremely high risk — IV crush + gap down can cause immediate
  assignment. A low-capital trader following this scanner into an earnings event will get destroyed.
- **Fix**: Fetch earnings dates from yfinance (`ticker.calendar`) and add a warning column:
  `⚠ Earnings in 3d` if an earnings event falls inside the contract window.

**4. No concept of capital required**
- The table shows Premium, Strike, Delta — but nowhere does it show **"cash you need to hold"**.
  For a trader with $10K, a TSLA $200 put = $20,000 required. The scanner has this data
  (`cash_needed = strike × 100`) but it's never shown in the UI.
- A beginner will see "TSLA $200 put, yield 8%" and not realize they need $20,000 to sell one
  contract. They only have $10,000. The trade is impossible for them.
- **Fix**: Add a "Capital Required" column ($) to the table. Add a capital filter: "Show only
  contracts I can afford" with a user-set account size input.

**5. Yield calculation inflates numbers for short-DTE options**
- `risk_adjusted_yield = (premium / (strike - premium)) / years × 100`
- A weekly option (7 DTE) with $1 premium on a $100 strike = (1/99) / (7/365) × 100 = **52.6% annualized**
- This number is technically correct but completely misleading. Annualizing a weekly return assumes
  you will successfully sell 52 puts per year with zero assignments. One assignment destroys months
  of gains. New traders chase these numbers and get wrecked.
- **Fix**: Add a "Realistic Yield" column that applies a probability-of-profit haircut:
  `realistic_yield = risk_adj_yield × (1 + delta)` (since delta ≈ probability of being ITM at expiry,
  `1 + delta` ≈ probability of expiring worthless for a put).

---

### 🟡 Important Gaps (reduce usefulness significantly)

**6. No current stock price in the web UI**
- The table shows Strike, OTM%, Delta — but not the **current stock price**.
- A trader can't judge if $180 strike on AAPL is reasonable without knowing AAPL is at $195 vs $182.
- The data exists in the output (`current_price` field) but is not displayed.
- **Fix**: Add `Price` column (current stock price) as the second column after Symbol.

**7. Implied Volatility not shown**
- IV is the single most important input for options pricing. High IV = expensive premium (good for sellers).
  Low IV = cheap premium (bad time to sell).
- Without IV, a trader cannot answer: "Is this premium actually rich, or is this stock just volatile?"
- The data exists in every output row (`implied_volatility` from yfinance).
- **Fix**: Add `IV %` column to the table.

**8. Theta not shown**
- Theta = dollars earned per day from time decay. For a low-capital trader this is the most
  intuitive metric: "This contract makes me $4.50/day just from the passage of time."
- The scanner calculates theta (in `indicators.py`) but never surfaces it in any output.
- **Fix**: Add `Theta/day ($)` column = `theta × 100` (per contract, not per share).

**9. No position sizing guidance**
- Correct wheel strategy position sizing: never more than 5–10% of portfolio in any single underlying.
  A $10K account should sell max 1 contract on any stock under $200 (requires $20K). Most positions
  are impossible without at least $15K–$20K.
- The platform gives zero guidance on this. A user with $5K will scan, see attractive yields,
  and be unable to trade any of them because the capital requirements are too high.
- **Fix**: Add a "Works for you" filter based on user's stated account size. Stocks like AAPL ($190)
  require $19,000 per contract — filter these out for small accounts.

**10. Backtest is not a backtest**
- `scanner/backtest.py` only counts how many contracts would have qualified on a given day.
  It does not simulate: P&L, assignment outcomes, roll decisions, or actual returns.
- The plan.md calls it a "back-testing harness" — this is misleading. It is an opportunity counter.
- A real trader needs to know: "If I had sold this put 6 months ago, what would have happened?"
- **Fix (Phase 2)**: Build a real backtest that simulates: entry premium, assignment check at expiry,
  stock ownership if assigned, covered call selling from assignment, P&L tracking across the full wheel.

---

### 🟢 What the Platform Does Well (keep these)

- Clean, honest UI. "Research only · no trades placed" is the right framing.
- The 45-Day default DTE preset is correct — it is the theta sweet spot.
- Delta range −0.10 to −0.30 is appropriate for CSP selling (high probability of profit).
- The Balanced tab scoring (40% yield + 30% OI + 30% delta) is reasonable.
- Safest/Highest Yield/Balanced three-way split gives good entry points for different risk tolerances.
- Minimum 1M avg volume requirement is smart — it prevents illiquid underlying traps.
- Bid-ask spread ≤ 10% filter is appropriate.

---

## Recommended Implementation Plan

### Phase 1 — Fix the dangerous gaps (immediate, high impact)

**1a. Add Capital Required column + account size filter**
- Files: `web/templates/index.html`, `web/static/js/dashboard.js`, `web/static/css/dashboard.css`
- Add `capital_required` field = `strike × 100` to every output row (already computed as `cash_needed`
  in `options_scanner.py` line 305 — just needs to be passed through to the web output)
- Add a "My Account Size" input in the scan bar (stored in localStorage)
- Add filter: hide rows where `capital_required > account_size`
- Add "Capital" column to table showing e.g. `$19,500`

**1b. Add current price, IV, and Theta columns to the table**
- `current_price` already in output CSV — add to web payload in `web/results_loader.py`
- `implied_volatility` already in output CSV
- `theta` is calculated in `scanner/indicators.py` but not saved — add to `options_scanner.py`
  fieldnames list (line 573) and pass through
- Add three columns to `index.html` table: `Price`, `IV %`, `θ/day`
- Render in `dashboard.js`: theta displayed as `$X.XX/day per contract` (multiply by 100)

**1c. Add Earnings Warning**
- New function in `options_scanner.py`: `_get_next_earnings(symbol)` using `yf.Ticker(symbol).calendar`
- During `scan_stock()`, check if any earnings date falls within the contract window
- Add boolean field `earnings_in_window` and `days_to_earnings` to output
- Show `⚠ Xd` warning cell in table when earnings fall within contract DTE
- Yellow row highlight when `earnings_in_window = True`

**1d. Fix risk-free rate**
- File: `scanner/indicators.py`
- Add function `_fetch_risk_free_rate()` that fetches `^IRX` (13-week T-bill) from yfinance
  and converts annualized % to decimal
- Cache the result for the duration of a scan run (pass as parameter to `calculate_greeks()`)
- Fallback to 0.0525 (5.25%) if fetch fails

**1e. Rename "Flagged" and add risk warning**
- Rename tab label from "⭐ Flagged" to "⚡ High Yield" in `index.html`
- Add subtitle text: "High yield + deep OTM — verify IV is elevated before trading"
- Update `TAB_HINTS` in `dashboard.js`
- Update guide drawer text

**1f. Add Realistic Yield column**
- In `options_scanner.py` `calculate_metrics()`: add field
  `realistic_yield = risk_adjusted_yield × (1 + delta)` where delta is negative
  (so for delta = -0.15: realistic_yield = risk_adj × 0.85)
- This is the probability-weighted expected annualized return
- Show as a column in the table; make it the secondary sort key for the Balanced tab

### Phase 2 — Better stock selection (medium term)

**2a. Add IV Rank column**
- Fetch 52-week high/low IV from yfinance historical data
- `iv_rank = (current_iv - iv_52w_low) / (iv_52w_high - iv_52w_low) × 100`
- Show as `IVR %` column — green if > 50 (premium is rich), red if < 30 (premium is cheap)
- Add to scan filter: "Only show high IVR" checkbox

**2b. Add Stock Score card view (Best Stocks tab)**
- New `/api/stocks` endpoint aggregating per-ticker: best yield contract, avg IVR, trend signal
- New "Best Stocks" tab showing card grid: ticker, score gauge, best contract summary
- Answers the question: "Which stock should I sell a put on today?"

### Phase 3 — Real backtesting (future)

**3a. Replace opportunity-counter backtest with P&L simulator**
- Track: entry date, entry premium, expiry outcome (assigned/expired), P&L per trade
- Simulate the full wheel: CSP → assignment → covered call → called away/rolled
- Report: win rate, avg return per trade, max drawdown, annualized return

---

## Files to Modify

| Phase | File | Change |
|-------|------|--------|
| 1a | `options_scanner.py` | Ensure `cash_needed` / `capital_required` in output fieldnames |
| 1a | `web/templates/index.html` | Add Capital column, account size input in scan bar |
| 1a | `web/static/js/dashboard.js` | Account size localStorage, capital filter, column render |
| 1b | `options_scanner.py` | Add `theta_per_contract`, `implied_volatility` to fieldnames |
| 1b | `web/templates/index.html` | Add Price, IV%, θ/day columns |
| 1b | `web/results_loader.py` | Pass new fields through to API payload |
| 1c | `options_scanner.py` | Add `_get_next_earnings()`, `earnings_in_window`, `days_to_earnings` |
| 1c | `web/templates/index.html` | Earnings warning cell, yellow row class |
| 1c | `web/static/css/dashboard.css` | `.row-earnings` yellow highlight style |
| 1d | `scanner/indicators.py` | `_fetch_risk_free_rate()` from `^IRX`, fallback 0.0525 |
| 1e | `web/templates/index.html` | Rename Flagged tab, add warning subtitle |
| 1e | `web/static/js/dashboard.js` | Update TAB_HINTS |
| 1f | `options_scanner.py` | Add `realistic_yield` field to metrics |
| 1f | `web/templates/index.html` | Add Realistic Yield column |

## Reuse These Existing Functions

- `scanner/indicators.py:calculate_greeks()` — already computes theta; just needs to be surfaced
- `options_scanner.py:calculate_metrics()` — add `realistic_yield` and `theta_per_contract` here
- `options_scanner.py:_enrich_with_greeks()` — already calls `calculate_greeks`, theta is available
- `yf.Ticker(symbol).calendar` — earnings date fetch (same pattern as existing `.info` calls)
- `yf.Ticker("^IRX").info["regularMarketPrice"]` — T-bill rate fetch

## Verification

1. Run `python3 cli.py` (watchlist scan) — confirm new fields appear in outputs/
2. Open `http://127.0.0.1:5000` — confirm new columns visible: Price, IV%, θ/day, Capital, Realistic Yield
3. Set account size to $10,000 — confirm contracts requiring > $10K are hidden
4. Pick a ticker with upcoming earnings (check manually) — confirm ⚠ warning appears
5. Check that risk-free rate logged at scan start reflects current ^IRX value, not 2.54%
6. Click "⚡ High Yield" tab — confirm warning subtitle is visible

---

# CSP Scanner — Technical Data UI/UX Improvement Plan

## Context

The scanner now displays **11 new technical data points** per option (Tech Score, 5 pivot levels, 5 Bollinger Band metrics). However, these columns are **hidden by default**. When revealed, they show raw numbers with minimal visual context. A trader viewing these columns must:

1. **Mentally interpret raw values** — "213.81" for W.PP means nothing without context to current price
2. **Remember scoring rules from tooltips** — "≥70 = strong" vs "50-69 = marginal" must be memorized
3. **Check favorability manually** — Does "65.3%" for BB %B fall in the sweet 30-70% range? User has to calculate
4. **Piece together relationships** — Are pivot levels relevant to this strike? Which metric indicates risk?

This creates **cognitive friction**. The goal is to make technical signals **actionable at a glance** through:

- **Contextual color coding** — green (favorable) / amber (neutral) / red (risky)
- **Visual indicators** — gradient bars, sparklines for quantitative ranges
- **Comparison marks** — showing strike vs. pivot, price vs. mid-band relationships
- **Prominence boost** — Tech Score visible in base table, not hidden

---

## Recommended Approach

### Phase 1: Promote Tech Score to Base Table (High Impact, Low Effort)

**Goal:** Move Tech Score from hidden extra column to the primary table, showing the color badge (green/amber/red) prominently.

**Why:** Traders see technical quality at a glance without expanding columns. The color badge becomes the first signal for decision-making.

**Changes:**
- Insert Tech Score as column #7 in base table (after Real Yield %, before Capital)
- Always visible; no toggle needed
- Render with color badge: green ≥70, amber 50-69, red <50
- Adds only ~60px width

**Files:**
- `web/templates/index.html` — move Tech Score `<th>` from extra cols section to base cols
- `web/static/js/dashboard.js` — reorder `renderTable()` cell output to inject Tech Score earlier in the row
- No CSS changes needed (reuse existing `.tech-score` classes)

---

### Phase 2: Add Color-Coded Context to Pivot & BB Cells (Medium Effort, High Value)

**Goal:** When columns are expanded, cells show contextual background colors indicating favorability.

**Color Rules:**

**Pivot Columns (W.PP, W.S1, W.S2, M.PP, M.S1):**
- 🟢 **Green background**: Strike is BELOW this level (safer = good)
- ⚪ **Inherit**: Strike is ABOVE this level (riskier, but acceptable)
- 🔴 **Red text**: Price is significantly below this level (stock weak relative to pivot)

Example: Strike=$185, W.S1=$190 → green background (strike below S1 = good safety cushion)

**BB %B (Band Position %):**
- 🟢 **Green bg**: 30–70% (sweet spot, ideal for selling)
- 🟡 **Amber bg**: 20–30% or 70–80% (approaching edge, caution)
- 🔴 **Red bg**: <20% or >80% (oversold/overbought, risky)

**BB Width (Volatility Regime %):**
- 🟢 **Green bg**: <10% (squeeze, stable, theta-friendly)
- 🟡 **Light amber bg**: 10–20% (normal)
- 🟡 **Darker amber bg**: 20–30% (expanding, caution)
- 🔴 **Red bg**: ≥30% (high vol, directional move likely)

**Changes:**
- `web/static/css/dashboard.css` — add `.cell-pivot-safe`, `.cell-pivot-risky`, `.cell-bb-sweet`, `.cell-bb-caution`, `.cell-bb-risky` classes
- `web/static/js/dashboard.js` — add helper `cellClassForPivot(strike, level)` and `cellClassForBB(metricType, value)` to determine class per cell
- Apply class to `<td>` at render time

**Benefit:** Trader sees at a glance which metrics are favorable. No mental math needed.

---

### Phase 3: Add Visual Gradient Bar for BB %B (Nice-to-Have)

**Goal:** For BB %B column, display a horizontal gradient bar (0–100%) with a marker showing current position instead of just text.

**Design:**
- Gradient bar: left (red, lower band) → center (white, mid) → right (red, upper band)
- Position marker: vertical line at the %B percentage
- Label: "65.3%" centered on bar
- Height: 24px

Visual:
```
[████████| ████] 65.3%
← Lower     Mid    Upper →
```

**Changes:**
- `web/static/css/dashboard.css` — `.bb-pct-bar` styles with gradient
- `web/static/js/dashboard.js` — render BB %B as HTML fragment with embedded SVG or CSS gradient + marker

---

### Phase 4: Enhance Banded Picks Summary Cards

**Goal:** Banded picks show Tech Score color badge prominently and add one-line tech context.

**Changes:**
- Move Tech Score badge to top-right of card (match KPI card styling)
- Add line: "Pivot status: Strike is $5 below W.S1 ✅"
- Add line: "BB position: 65% (sweet spot) ✅"

Example:
```
CONSERVATIVE (|Δ| ≤ 0.15)

DELL                                    ⭐ 68/100
Strike $120  |  Expiry Jul 24 (44d)
Premium $2.85  |  Yield 19.4%

Pivot status: Strike $5 below W.S1 ✅
BB position: 65% of band (sweet zone) ✅
```

**Files:**
- `web/static/js/dashboard.js` — enhance `renderBandedPicks()` function
- `web/static/css/dashboard.css` — `.band-tech` styling to make badge larger

---

### Phase 5: Streamline Tooltips

**Goal:** Make tooltips more actionable, less text-heavy.

**Changes:**
- Shorten text to 2 sentences max (currently long paragraphs)
- End with decision guidance: "✅ Enter" or "⚠️ Caution" or "⛔ Avoid"
- Add "[Learn more →](#guide)" link for deep dives

Example new tooltip for Tech Score:
> **Tech Score (0–100)**
>
> Composite signal for entry quality. ≥70 = ✅ Strong | 50–69 = ⚠️ Marginal | <50 = ⛔ Weak
>
> [Learn more →](#guide)

**Files:**
- `web/templates/index.html` — shorten `data-tip` text on all tech column headers

---

## Implementation Priority

### Must-Have (High impact, low effort):
1. **Phase 1** — Tech Score always visible (30 min)
2. **Phase 2** — Color-coded pivot & BB cells (1 hr)
3. **Phase 5** — Tooltip rewrite (20 min)

**Subtotal: ~1.5 hours**

### Nice-to-Have (Good UX, medium effort):
4. **Phase 3** — Gradient bar for BB %B (1.5 hrs SVG/CSS)
5. **Phase 4** — Banded picks context lines (45 min)

**Subtotal: ~2 hours**

**Grand Total: ~3.5 hours for all phases | ~1.5 hours for must-haves only**

---

## Expected Outcome

**Before Improvements:**
- User expands columns, sees 15+ columns of numbers and dollar signs
- Must read tooltips to understand each metric
- Banded picks show minimal context

**After Improvements:**
- Tech Score visible in base table with color badge
- Expanded columns show contextual coloring: green/amber/red backgrounds indicate decision quality
- BB %B displays as visual gradient, not text
- Banded picks include one-line tech context
- Trader can scan and make trades **2–3x faster** with higher confidence

---

## Files to Modify

1. **web/templates/index.html** — Move Tech Score header, shorten tooltips
2. **web/static/js/dashboard.js** — Reorder table cells, add color-determination helpers, enhance banded picks
3. **web/static/css/dashboard.css** — Add cell background color classes, gradient bar styles

---

## Verification Checklist

**Phase 1 (Tech Score visible):**
- [ ] Reload dashboard, Tech Score appears as 7th column in base table
- [ ] Color badges render: green ≥70, amber 50-69, red <50
- [ ] Click ⊕ More Columns, Tech Score also appears in extra section (not duplicated)

**Phase 2 (Color-coded cells):**
- [ ] Expand columns
- [ ] Strike=$185, W.S1=$190 → green background
- [ ] BB %B=65% → green background
- [ ] BB %B=15% → red background
- [ ] BB Width=8% → green background
- [ ] BB Width=35% → red background

**Phase 3 (Gradient bars):**
- [ ] BB %B renders as gradient bar with marker
- [ ] Tooltip still shows on hover, doesn't overlap
- [ ] Bar width fits cell at 100% zoom

**Phase 4 (Banded picks):**
- [ ] View banded picks cards
- [ ] Tech Score badge visible and color-coded
- [ ] Pivot status line shows comparison
- [ ] BB position line shows percentage + interpretation

**Phase 5 (Tooltips):**
- [ ] Hover each tech column header
- [ ] Tooltip is <3 sentences
- [ ] Ends with decision guidance (✅/⚠️/⛔)

---

## Code Reuse

1. **`techBand(score)`** — already maps score to color class; extend to include decision guidance
2. **`.tech-score` CSS classes** — reuse for new `.cell-*` classes using same palette
3. **Tooltip system** (`initTooltips()`) — already handles hover/positioning; just update HTML content
4. **`fmtPivot()` / `fmt1()` helpers** — no changes needed; cell coloring applied via CSS class
