# Quick Start: CSP Performance Tracking System

**Get your Alpaca trades loaded and analyzed in 5 minutes**

---

## 1️⃣ Install Dependencies
```bash
cd /Users/sathishkumar/Documents/claude/Trading
pip install -r requirements.txt
```

## 2️⃣ Start the Server
```bash
python -m web.app
```

**Output should show:**
```
Configuration loaded: <Config host=127.0.0.1 port=5000 debug=True database=data/trades.db>
Database initialized successfully
Registered trade routes blueprint
```

## 3️⃣ Open Browser
```
http://localhost:5000
```

## 4️⃣ Add Alpaca Credentials
1. Click **⚙️ Alpaca** button (top right)
2. Enter your API Key and Secret (from https://app.alpaca.markets/paper-trading/overview)
3. Click **Save All Settings**

## 5️⃣ Sync Your Trades
1. Click **📊 Trade Journal** tab
2. Click **🔄 Sync from Alpaca** button
3. Wait for "Sync completed" message
4. Your trades now appear in the journal!

## 6️⃣ View Your Performance
1. Click **📈 Performance** tab
2. See your metrics:
   - Win Rate (target: >65%)
   - Average ROI per trade
   - Sharpe Ratio (risk-adjusted returns)
   - Cumulative P&L charts

## 7️⃣ Analyze Your Strategy
1. Click **🎯 Strategy** tab
2. Switch between views:
   - **Delta Band**: Conservative/Standard/Aggressive
   - **DTE Window**: Weekly/Short/Medium/Long
   - **By Symbol**: Which stocks work best?

---

## What You Get

### 📊 Trade Journal
- All your trades in one place
- Win/loss status
- P&L per trade
- ROI percentage
- Sortable and filterable

### 📈 Performance Dashboard
- **Win Rate**: % of profitable trades
- **Average ROI**: Return per trade
- **Sharpe Ratio**: Risk-adjusted performance
- **Charts**: Monthly P&L, Cumulative growth
- **Metrics**: Max drawdown, total trades

### 🎯 Strategy Analysis
- Compare delta bands (risk levels)
- Compare DTE windows (time horizons)
- Identify best-performing symbols
- See which strategies work for you

---

## Pro Tips

### 1. Sync Regularly
Every few days, click "Sync from Alpaca" to pull in new closed trades.

### 2. Edit Trades
Click any trade to:
- Add notes about why you chose it
- Update pivot levels
- Adjust tech score
- P&L recalculates automatically

### 3. Find Your Edge
In Strategy Analysis, look for patterns:
- Which delta bands perform best?
- Which DTE windows have highest win rate?
- Which symbols are most profitable?

### 4. Track Over Time
Come back monthly to see:
- Win rate trends
- Monthly P&L progression
- Which strategies are working

---

## Common Actions

### Add a New Trade Manually
*Coming soon* - Trade entry form in dashboard

### Export Data
*Coming soon* - CSV/PDF export of trades and performance

### Set Alerts
*Coming soon* - Notifications for trade milestones

---

## Environment Variables (Optional)

If you want to customize:
```bash
export PORT=5000              # Change port
export DEBUG=false            # Disable debug mode
export DATABASE_PATH=/path    # Custom database location
```

Then run: `python -m web.app`

---

## Troubleshooting

### "Cannot connect to localhost:5000"
- Make sure the server is running
- Check that port 5000 is not in use: `lsof -i :5000`

### "No trades appear"
- Verify Alpaca credentials are correct
- Check that you have filled option orders
- Try the manual sync guide: `SYNC_TRADES_GUIDE.md`

### Metrics show all zeros
- No closed trades in database yet
- Sync from Alpaca first
- Or create a test trade manually

---

## Next Steps

1. ✅ Sync your Alpaca trades
2. ✅ Review performance in dashboard
3. ✅ Analyze strategy by different breakdowns
4. ✅ Identify your edge (what works best)
5. ✅ Track performance month-to-month

---

## Files & Docs

For more details:
- **FIX_SUMMARY.md** - What was fixed and how
- **SYNC_TRADES_GUIDE.md** - Detailed sync instructions
- **FULL_IMPLEMENTATION_SUMMARY.md** - Complete technical docs
- **VERIFICATION_CHECKLIST.md** - Pre-launch checklist

---

## Your System is Ready! 🚀

Everything is set up and working. Just:
1. Run the server
2. Open the dashboard
3. Add credentials
4. Click "Sync from Alpaca"
5. Watch your trades load and analyze!

**Questions? Check the docs or examine the code - everything follows best practices and is well-documented.**
