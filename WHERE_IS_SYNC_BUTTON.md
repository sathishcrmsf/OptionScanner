# Where is the "Sync from Alpaca" Button?

## The Complete Path

### Step 1: Open Dashboard
```
http://localhost:5000
```

### Step 2: Set Alpaca Credentials (If Not Done Yet)
1. Click **⚙️ Alpaca** button in top-right corner
2. Enter your API Key and Secret
3. Click **Save All Settings**

### Step 3: Click the "📊 Trade Journal" Tab
Look at the row of tabs below the scan configuration:
- All
- ⚡ High Yield
- Safest
- Highest Yield
- Balanced
- **📊 Trade Journal** ← Click this one

When you click it:
- The scanner results table will disappear
- The Trade Journal will load
- You'll see two possible screens:

### Step 4A: If You Have No Trades Yet
You'll see an empty state with two buttons:
```
┌─────────────────────────────────────┐
│  No trades recorded yet.            │
│                                     │
│  [🔄 Sync from Alpaca]  [➕ New]  │
└─────────────────────────────────────┘
```

**Click "🔄 Sync from Alpaca"** - This is the button!

### Step 4B: If You Already Have Trades
You'll see a trade journal with a stats row at the top:
```
┌─────────────────────────────┐
│ Total  │ Open │ Closed │ WR │ P&L │ 🔄 │
│  15    │  3   │  12    │87% │$520 │    │
└─────────────────────────────┘
```

**Click the "🔄 Sync Alpaca" button** in the stats row on the right

## What The Button Does

When you click "🔄 Sync from Alpaca":

1. ✅ Fetches all your filled option orders from Alpaca (last 90 days)
2. ✅ Parses the option symbols to extract: Symbol, Strike, Expiration
3. ✅ Creates new trades in the database
4. ✅ Updates existing trades with exit details
5. ✅ Calculates P&L from filled prices
6. ✅ Refreshes the Trade Journal display
7. ✅ Updates Performance metrics

## Complete Journey

```
Dashboard (http://localhost:5000)
    ↓
Click "⚙️ Alpaca" → Enter credentials → Save
    ↓
Click "📊 Trade Journal" tab
    ↓
See empty state OR trades with stats
    ↓
Click "🔄 Sync from Alpaca" button
    ↓
Button shows "⏳ Syncing..."
    ↓
Server fetches from Alpaca API
    ↓
Database updated with your trades
    ↓
"Sync completed: X trades created, Y updated"
    ↓
Trade Journal refreshes with your trades
    ↓
View performance in other tabs
```

## If You Don't See the Button

### Check 1: Are you on the Trade Journal tab?
- Look for the tabs row: `All | High Yield | Safest | ... | 📊 Trade Journal`
- The Trade Journal tab should be near the right side

### Check 2: Did you set Alpaca credentials?
- Click "⚙️ Alpaca" button (top right)
- Enter your API Key and Secret
- Click "Save All Settings"
- Then click Trade Journal tab again

### Check 3: Browser Console
Open Developer Tools (F12) and check Console tab:
- If you see errors like "loadTradeJournal is not defined"
- Reload the page with Ctrl+Shift+R (hard refresh)

### Check 4: Make Sure You're Looking at the Right Tab
The button appears in the Trade Journal tab only. Not in:
- ❌ All (scanner results)
- ❌ Safest (scanner results)
- ❌ Balanced (scanner results)
- ❌ Positions (Alpaca positions)
- ❌ Orders (Alpaca orders)

It only appears in:
- ✅ **📊 Trade Journal** ← This one!

## Example Screenshots (Text)

### Empty State
```
┌──────────────────────────────────────────┐
│                                          │
│        No trades recorded yet.           │
│                                          │
│  [🔄 Sync from Alpaca] [➕ New Trade]   │
│                                          │
└──────────────────────────────────────────┘
```

### With Trades
```
┌─────────────────────────────────────────────────────┐
│ Total: 15  Open: 3  Closed: 12  WR: 87%  P&L: $520│
│                                      [🔄 Sync Alpaca] │
├─────────────────────────────────────────────────────┤
│ Symbol │ Entry Date │ Strike │ Premium │ Status │ P&L│
├─────────────────────────────────────────────────────┤
│ AAPL   │ 2026-05-15 │ $180   │ $2.50   │ Closed │ $45│
│ MSFT   │ 2026-05-20 │ $380   │ $3.20   │ Closed │-$12│
│ ...    │ ...        │ ...    │ ...     │ ...    │ ...│
└─────────────────────────────────────────────────────┘
```

## If It Still Doesn't Work

1. **Restart the server:**
   ```bash
   # Stop: Press Ctrl+C
   # Start: python -m web.app
   ```

2. **Hard refresh the browser:**
   ```
   Ctrl+Shift+R (or Cmd+Shift+R on Mac)
   ```

3. **Check browser console for errors:**
   ```
   F12 → Console tab → Look for red errors
   ```

4. **Verify performance.js loaded:**
   ```
   F12 → Sources tab → Check web/static/js/performance.js exists
   ```

---

## Still Can't Find It?

The button location is:
1. Open http://localhost:5000
2. Click the **📊 Trade Journal** tab
3. Look for the **🔄 Sync from Alpaca** button

It's a green/blue button with:
- Icon: 🔄 (spinning arrow)
- Text: "Sync from Alpaca" OR "Sync Alpaca"

**The button ONLY appears in the Trade Journal tab.**

---

**Got it? Now go sync your trades!** 🚀
