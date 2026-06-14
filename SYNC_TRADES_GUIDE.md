# How to Sync Your Alpaca Trades

## Overview

The system now supports syncing your closed positions from Alpaca directly into the trade journal. This pulls all your filled option orders from the last 90 days and creates trades in the database automatically.

## How to Sync

### Option 1: Using the Dashboard (When Implemented)
In the Trade Journal tab, there will be a "🔄 Sync from Alpaca" button. Click it and your trades will be synced automatically.

### Option 2: Using cURL (Right Now)

```bash
curl -X POST http://localhost:5000/api/trades/sync-alpaca \
  -H "X-APCA-Key: YOUR_ALPACA_API_KEY" \
  -H "X-APCA-Secret: YOUR_ALPACA_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Replace `YOUR_ALPACA_API_KEY` and `YOUR_ALPACA_API_SECRET` with your actual Alpaca credentials.

### Option 3: Using Python

```python
import requests

response = requests.post(
    'http://localhost:5000/api/trades/sync-alpaca',
    headers={
        'X-APCA-Key': 'YOUR_ALPACA_API_KEY',
        'X-APCA-Secret': 'YOUR_ALPACA_API_SECRET',
    },
    params={
        'days_back': 90  # Optional, default is 90
    }
)

print(response.json())
# Output:
# {
#   "synced": 15,
#   "created": 12,
#   "updated": 3,
#   "message": "Sync completed: 12 trades created, 3 updated"
# }
```

## What Happens During Sync

1. **Fetches Closed Orders**: Pulls all FILLED option orders from Alpaca (last 90 days by default)
2. **Parses Option Symbols**: Extracts underlying symbol, strike, and expiration from OCC-format symbols
3. **Matches Existing Trades**: Looks for existing trades for the same symbol/strike/expiration
4. **Creates New Trades**: For unmatched orders, creates new trade entries
5. **Updates Existing Trades**: For matched orders, updates with exit details and P&L

## Example Response

```json
{
  "synced": 15,
  "created": 12,
  "updated": 3,
  "errors": null,
  "message": "Sync completed: 12 trades created, 3 updated"
}
```

### Response Fields
- **synced**: Total number of orders processed from Alpaca
- **created**: New trades created in the database
- **updated**: Existing trades updated with exit information
- **errors**: Any errors that occurred during sync (null if none)
- **message**: Human-readable summary

## Query Parameters

### days_back (Optional)
Number of days to look back for closed orders.
- Default: `90`
- Min: `1`
- Max: `365`

Example: Get trades from the last 30 days only
```bash
curl -X POST http://localhost:5000/api/trades/sync-alpaca?days_back=30 \
  -H "X-APCA-Key: YOUR_KEY" \
  -H "X-APCA-Secret: YOUR_SECRET"
```

## Trade Details Auto-Filled from Alpaca

When a trade is synced from Alpaca:
- ✅ Symbol (from option contract)
- ✅ Strike (from option contract)
- ✅ Expiration (from option contract)
- ✅ Premium Received (from limit price of the order)
- ✅ Buy Back Price (from filled average price)
- ✅ Exit Date (from when order was filled)
- ⚠️ Entry Tech Score (defaults to 50, can be edited later)
- ⚠️ Pivot Levels (defaults to null, can be edited later)
- ⚠️ DTE at Entry (calculated as 0, can be edited later)

## Manual Override

After syncing, you can:
1. View the synced trade in the Trade Journal tab
2. Click the row to expand details
3. Edit any field (notes, pivot levels, tech score)
4. The P&L will be automatically recalculated

## Example Workflow

### Step 1: Check Current Trades
```bash
curl http://localhost:5000/api/trades \
  -H "X-APCA-Key: YOUR_KEY"
# Shows: 0 trades (empty database)
```

### Step 2: Sync from Alpaca
```bash
curl -X POST http://localhost:5000/api/trades/sync-alpaca \
  -H "X-APCA-Key: YOUR_KEY" \
  -H "X-APCA-Secret: YOUR_SECRET"
# Creates 12 trades from your Alpaca orders
```

### Step 3: View Synced Trades
```bash
curl http://localhost:5000/api/trades
# Shows: 12 trades now in database with P&L calculated
```

### Step 4: View Performance
```bash
curl http://localhost:5000/api/performance
# Shows: Win rate, ROI, Sharpe ratio, etc. based on synced trades
```

## Troubleshooting

### Error: "Missing Alpaca credentials in headers"
Make sure you're sending both:
- `-H "X-APCA-Key: YOUR_KEY"`
- `-H "X-APCA-Secret: YOUR_SECRET"`

### Error: "Failed to sync with Alpaca"
Verify:
1. Your Alpaca API credentials are correct
2. Your internet connection is working
3. Alpaca API is accessible (https://paper-api.alpaca.markets)
4. Check the server logs for details: `tail -f logs/`

### No trades synced but I have orders on Alpaca
Check:
1. Are the orders **FILLED** (not pending or cancelled)?
2. Were they filled in the last **90 days**?
3. Try with a larger `days_back` parameter: `?days_back=365`

## What's Next

After syncing your trades:
1. Go to the **Trade Journal** tab to see all trades
2. Go to the **Performance** tab to see metrics and charts
3. Go to the **Strategy** tab to analyze by delta band/DTE/symbol
4. Edit trades to add notes, pivot levels, tech scores if desired

---

**Note:** Syncing is idempotent - you can run it multiple times without creating duplicates. If a trade already exists with the same symbol/strike/expiration, it will update the existing trade instead of creating a new one.
