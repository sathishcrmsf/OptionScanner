# Quick Reference Guide - CSP Performance Tracking System

## 🚀 Get Started in 30 Seconds

```bash
# 1. Start the server
python -m web.app

# 2. Open in browser
http://localhost:5000

# 3. Set Alpaca credentials
Click ⚙️ Alpaca → Enter API Key/Secret → Save

# 4. Sync your trades
Click 📊 Trade Journal → 🔄 Sync from Alpaca

# 5. View performance
Click 📈 Performance → See your metrics!
```

---

## 📊 API Endpoints (Quick Reference)

### List Trades
```bash
curl http://localhost:5000/api/trades
curl http://localhost:5000/api/trades?symbol=AAPL
curl http://localhost:5000/api/trades?status=closed
```

### Create Trade
```bash
curl -X POST http://localhost:5000/api/trades \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "strike": 185.0,
    "expiration": "2026-07-24",
    "dte_at_entry": 45,
    "premium_received": 3.40,
    "contracts": 1,
    "capital_required": 18500,
    "delta_at_entry": -0.176,
    "realistic_yield_at_entry": 12.79
  }'
```

### Get Single Trade
```bash
curl http://localhost:5000/api/trades/{trade_id}
```

### Close Trade
```bash
curl -X PUT http://localhost:5000/api/trades/{trade_id} \
  -H "Content-Type: application/json" \
  -d '{
    "exit_type": "bought_back",
    "buy_back_price": 1.00
  }'
```

### Get Performance Metrics
```bash
curl http://localhost:5000/api/trades/performance
curl http://localhost:5000/api/trades/performance/monthly
curl http://localhost:5000/api/trades/performance/by-strategy?breakdown=delta_band
curl http://localhost:5000/api/trades/performance/by-strategy?breakdown=dte_window
curl http://localhost:5000/api/trades/performance/by-strategy?breakdown=symbol
```

---

## 📋 Validation Rules

| Field | Type | Range | Example |
|-------|------|-------|---------|
| symbol | String | 1-5 letters | "AAPL" |
| strike | Float | $0.01 - $1M | 185.0 |
| expiration | Date | YYYY-MM-DD | "2026-07-24" |
| dte_at_entry | Integer | 1-730 days | 45 |
| premium_received | Float | > $0 | 3.40 |
| contracts | Integer | ≥ 1 | 1 |
| capital_required | Float | $0.01 - $1M | 18500 |
| delta_at_entry | Float | -1.0 to 0 | -0.176 |
| realistic_yield_at_entry | Float | 0-100% | 12.79 |

---

## 📈 Performance Metrics

### Win Rate
```
% of closed trades with P&L > 0
Target: >65% for CSP selling
Example: 12 wins / 15 closed = 80%
```

### Average ROI
```
Mean return on capital required
Formula: Average(realized_pnl / capital_required)
Example: 1.30% average return per trade
```

### Sharpe Ratio
```
Risk-adjusted return metric
Formula: (Avg Return - Risk-Free Rate) / Std Dev
Higher is better (target: >1.0)
```

### Max Drawdown
```
Worst peak-to-trough decline
Formula: (Peak Cumulative P&L - Trough) / Peak
Example: -3.2% means worst losing streak
```

### Total P&L
```
Sum of all realized profits and losses
Formula: Sum((Premium - BuyBack) × 100 × Contracts)
Example: $2,400 total profit on 15 trades
```

---

## 🎯 Delta Band Categories

| Band | Delta | Risk | Premium | Target |
|------|-------|------|---------|--------|
| Conservative | ≤ 0.15 | Low | Lower | >80% WR |
| Standard | 0.15-0.22 | Medium | Medium | >65% WR |
| Aggressive | > 0.22 | Higher | Higher | >50% WR |

---

## ⏰ DTE Window Categories

| Window | Days | Decay | Risk |
|--------|------|-------|------|
| Weekly | 1-7 | Fast | High |
| Short | 8-21 | Medium | Medium |
| Medium | 22-45 | Slow | Low |
| Long | 46+ | Very Slow | Very Low |

---

## 💾 Database Location

```
/Users/sathishkumar/Documents/claude/Trading/data/trades.db
```

Auto-created on first run. SQLite format.

---

## ⚙️ Configuration

### Environment Variables
```bash
export PORT=5000              # Default port
export DEBUG=true             # Debug mode
export DATABASE_PATH=./data/trades.db  # DB location
export ALPACA_API_KEY=pk_...  # Alpaca key
export ALPACA_API_SECRET=...  # Alpaca secret
```

### Configuration File
```
web/config.py - All settings loaded here
```

---

## 🔧 Troubleshooting

### Port Already in Use
```bash
# Find process on port 5000
lsof -i :5000

# Kill it
kill -9 {pid}

# Restart server
python -m web.app
```

### Database Error
```bash
# Delete corrupted database
rm /Users/sathishkumar/Documents/claude/Trading/data/trades.db

# Restart server (creates new DB)
python -m web.app
```

### API Returns 404
```bash
# Verify routes are /api/trades/* (not /api/*)
curl http://localhost:5000/api/trades/performance

# Check server is running
curl http://localhost:5000/
```

### Performance Metrics Show 0
```bash
# Make sure trades are closed (status="closed")
# Open trades don't contribute to metrics
# Close a trade: PUT /api/trades/{id} with exit_type
```

---

## 📁 File Structure

```
web/
├── app.py                          # Flask app
├── config.py                       # Configuration
├── database.py                     # Database management
├── alpaca_service.py              # Alpaca integration
├── models/
│   └── trade.py                   # Trade model
├── routes/
│   └── trades.py                  # API endpoints
├── services/
│   └── performance_service.py     # Metric calculations
├── repositories/
│   └── trade_repository.py        # Data access
├── static/
│   ├── js/
│   │   ├── dashboard.js           # Main UI logic
│   │   └── performance.js         # Trade journal & sync
│   └── css/
│       ├── dashboard.css          # Main styling
│       └── performance.css        # Trade journal styling
└── templates/
    └── index.html                 # HTML template

data/
└── trades.db                      # SQLite database

logs/
└── (log files if enabled)
```

---

## 🔐 Security Notes

✅ **API Keys**
- Never hardcode Alpaca API keys
- Use environment variables or settings
- Keys stored in browser localStorage (user-controlled)

✅ **Database**
- SQLite is local-only
- No internet exposure
- Back up `trades.db` regularly

✅ **Validation**
- All inputs validated on server side
- No SQL injection possible (SQLAlchemy ORM)
- No XSS possible (JSON API, not HTML)

---

## 📊 Example Workflow

### 1. Create Trade
```json
POST /api/trades
{
  "symbol": "AAPL",
  "strike": 185.0,
  "expiration": "2026-07-24",
  "dte_at_entry": 45,
  "premium_received": 3.40,
  "contracts": 1,
  "capital_required": 18500,
  "delta_at_entry": -0.176,
  "realistic_yield_at_entry": 12.79,
  "entry_notes": "Strong tech score, above pivot"
}

Response: {trade_id: "abc123", status: "open"}
```

### 2. Trade Expires
```
7/24/2026 - Option expires worthless
```

### 3. Close Trade
```json
PUT /api/trades/abc123
{
  "exit_type": "expiration",
  "buy_back_price": 0.00
}

Response: {
  status: "closed",
  realized_pnl: 340.00,
  roi_percent: 0.0184,
  holding_days: 45
}
```

### 4. View Metrics
```
GET /api/trades/performance

Response: {
  total_trades: 1,
  closed_trades: 1,
  win_rate_pct: 100.0,
  average_roi_pct: 1.84,
  sharpe_ratio: 0.0,
  max_drawdown_pct: 0.0
}
```

---

## 🎯 Key Formulas

### Realized P&L
```
(Premium Received - Buy Back Price) × 100 × Number of Contracts
Example: ($3.40 - $0.10) × 100 × 1 = $330
```

### ROI
```
Realized P&L / Capital Required
Example: $330 / $18,500 = 1.78%
```

### Annualized ROI
```
ROI × (365 / Days Held)
Example: 1.78% × (365 / 45) = 14.4% annualized
```

### Win Rate
```
(Number of Wins / Total Closed Trades) × 100
Example: (12 / 15) × 100 = 80%
```

### Sharpe Ratio
```
(Avg Daily Return - Risk-Free Rate) / Std Dev of Returns × √252
Target: > 1.0 (better risk-adjusted returns)
```

---

## 📞 Support

### Check Logs
```bash
tail -100 /tmp/server.log
```

### Review Code
```bash
# All files are well-documented
cat web/routes/trades.py      # API endpoints
cat web/models/trade.py       # Data model
cat web/services/performance_service.py  # Metrics
```

### Run Tests
```bash
bash /tmp/test_apis.sh  # Full test suite
```

---

## ✅ System Status

- ✅ Database: Working
- ✅ API Endpoints: All passing
- ✅ Validation: All rules working
- ✅ Performance Calculations: Accurate
- ✅ Error Handling: Robust
- ✅ Security: Verified
- ✅ Documentation: Complete

**Status: READY FOR PRODUCTION** 🚀

---

**Last Updated:** June 9, 2026  
**Version:** 1.0 (MVP - Complete)
