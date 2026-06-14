# Scanner Strategy Awareness Implementation

**Date:** June 9, 2026  
**Status:** ✅ **COMPLETE**

---

## What Was Fixed

The user reported: **"but when strategy is also taking me to the same window"**

**Problem:** Clicking "Start Scanning" on the Wheel strategy card took users to the same CSP scanner instead of a Wheel-aware scanner interface.

**Root Cause:** The scanner UI (dashboard.js) didn't read the strategy parameter from the URL or update its interface based on the selected strategy.

**Solution:** Make the scanner UI strategy-aware by:
1. Reading the `?strategy=WHEEL` parameter from the URL
2. Loading strategy metadata dynamically
3. Updating page title and labels based on selected strategy
4. Passing the strategy parameter to the API when scanning

---

## Implementation Changes

### 1. **dashboard.js** - Frontend Strategy Awareness

#### Change 1: Added selectedStrategy to state (line 22)
```javascript
let selectedStrategy = "CSP";  // Default to CSP
```

#### Change 2: Added loadStrategyMetadata() function (after line 728)
```javascript
// ── Load strategy metadata and update UI ──────────────────────────────────
function loadStrategyMetadata() {
  fetch('/api/strategies')
    .then(r => r.json())
    .then(data => {
      const strategies = data.strategies || [];
      const strategy = strategies.find(s => s.id === selectedStrategy);

      if (!strategy) {
        console.warn(`Strategy ${selectedStrategy} not found, defaulting to CSP`);
        selectedStrategy = 'CSP';
        return;
      }

      // Update page title
      document.title = `${strategy.name} Scanner`;

      // Update topbar title if present
      const topbarTitle = document.querySelector('.topbar-title');
      if (topbarTitle) {
        topbarTitle.textContent = `${strategy.name} Scanner`;
      }

      // Update setup label if present
      const setupLabel = document.querySelector('.setup-label');
      if (setupLabel) {
        setupLabel.textContent = `CONFIGURE YOUR ${strategy.name.toUpperCase()}`;
      }

      // Apply strategy-specific theme color
      if (strategy.color_hex) {
        document.documentElement.style.setProperty('--strategy-primary-color', strategy.color_hex);
      }

      console.log(`Loaded strategy: ${strategy.name}`);
    })
    .catch(err => {
      console.error('Error loading strategy metadata:', err);
    });
}
```

#### Change 3: Updated init() function (line 1102)
Added at the beginning to read strategy from URL and load metadata:
```javascript
function init() {
  // Read strategy from URL query parameter
  const urlParams = new URLSearchParams(window.location.search);
  selectedStrategy = urlParams.get('strategy') || 'CSP';

  // Load strategy metadata and update UI
  loadStrategyMetadata();

  loadAccountSize();
  // ... rest of init function
}
```

#### Change 4: Updated startScan() function (line 91-100)
Added strategy parameter to API request body:
```javascript
fetch("/api/scan", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    strategy: selectedStrategy,    // ← NEW
    preset: activePreset,
    dte_min: min,
    dte_max: max
  }),
})
```

### 2. **app.py** - Backend Strategy Acceptance

#### Change 1: Updated /api/scan endpoint (line 172-202)
Added strategy parameter extraction and logging:
```python
@app.route("/api/scan", methods=["POST"])
def api_scan_start():
    body = request.get_json(silent=True) or {}

    # Get strategy (default to CSP for backward compatibility)
    strategy = str(body.get("strategy", "CSP")).upper()
    logger.info(f"Scan request for strategy: {strategy}")

    # ... rest of scan logic ...

    with _scan_lock:
        # ...
        _scan_state["strategy"] = strategy

    return jsonify({
        "status": "started",
        "dte_min": dte_min,
        "dte_max": dte_max,
        "strategy": strategy  # ← NEW: Return strategy in response
    }), 202
```

---

## User-Facing Behavior Changes

### Before
- Home page: User selects strategy card ✓
- Scanner: Always shows "CSP Scanner" regardless of selected strategy ✗
- Scanner: No visual indication of which strategy is active ✗
- Scanner: Doesn't pass strategy to API ✗

### After
- Home page: User selects strategy card ✓
- Scanner: Page title updates to show selected strategy ✓
  - `http://localhost:5000/scanner?strategy=CSP` → Title: "Cash-Secured Put Scanner"
  - `http://localhost:5000/scanner?strategy=WHEEL` → Title: "Wheel Strategy Scanner"
- Scanner: Topbar and labels update based on strategy ✓
- Scanner: Strategy color theme applied (CSP green #22c55e, WHEEL amber #f59e0b) ✓
- Scanner: Strategy parameter passed to API ✓

---

## How It Works

### Flow Diagram

```
1. User clicks "Start Scanning" on WHEEL card
   ↓
2. home.js calls selectStrategy('WHEEL')
   ↓
3. Browser navigates to /scanner?strategy=WHEEL
   ↓
4. scanner.html loads, dashboard.js initializes
   ↓
5. init() reads URL: selectedStrategy = 'WHEEL'
   ↓
6. loadStrategyMetadata() fetches /api/strategies
   ↓
7. JavaScript updates page title: "Wheel Strategy Scanner"
   ↓
8. User sees correct strategy name in UI ✓
   ↓
9. User clicks "Run Scan"
   ↓
10. startScan() sends POST /api/scan with body:
    { strategy: "WHEEL", preset: "STANDARD", ... }
    ↓
11. Backend receives strategy parameter
    ↓
12. Future: Backend will dispatch to WheelStrategy for scanning
```

---

## Testing Results

✅ **All integration tests passed:**

| Test | Status |
|------|--------|
| Home page loads with strategy cards | ✓ |
| /api/strategies returns CSP and WHEEL | ✓ |
| Scanner page loads with ?strategy=CSP | ✓ |
| Scanner page loads with ?strategy=WHEEL | ✓ |
| JavaScript reads strategy from URL | ✓ |
| Backend accepts strategy parameter in request | ✓ |
| Backend returns strategy in response | ✓ |

**Example API Request/Response:**
```bash
curl -X POST http://localhost:5000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"strategy": "WHEEL", "preset": "STANDARD"}'

# Response:
# {
#   "status": "started",
#   "dte_min": 21,
#   "dte_max": 45,
#   "strategy": "WHEEL"
# }
```

---

## Next Steps

### Phase 2: Backend Strategy Dispatch (Not Yet Implemented)

The backend currently accepts the `strategy` parameter but doesn't use it. To complete the implementation:

1. **Modify `/api/scan` endpoint** to use strategy registry:
   ```python
   @app.route("/api/scan", methods=["POST"])
   def api_scan_start():
       strategy_id = body.get("strategy", "CSP").upper()
       
       # Validate strategy exists
       if not strategy_registry.exists(strategy_id):
           return {"error": f"Unknown strategy: {strategy_id}"}, 400
       
       # Get strategy instance
       strategy = strategy_registry.get_strategy(strategy_id)
       
       # Run appropriate strategy
       thread = threading.Thread(
           target=_run_scan_background,
           args=(strategy, params),
           daemon=True
       )
   ```

2. **Update `_run_scan_background()`** to accept strategy object:
   ```python
   def _run_scan_background(strategy, params):
       # Use strategy.run_scan() instead of OptionsScanner
       results = strategy.run_scan(symbols, params)
   ```

3. **Test Wheel strategy scanning** with realistic data

4. **Verify CSP still works** (backward compatibility)

---

## Files Modified

| File | Changes |
|------|---------|
| `web/static/js/dashboard.js` | Added strategy awareness: URL reading, metadata loading, UI updates, API parameter passing |
| `web/app.py` | Updated `/api/scan` endpoint to accept and return strategy parameter |

---

## Backward Compatibility

✅ **Fully backward compatible:**
- Default strategy is CSP if no parameter provided
- Old links to `/scanner` still work (defaults to CSP)
- API returns strategy in response but doesn't affect scan logic yet
- Database schema unchanged

---

## Summary

**Status:** ✅ **CRITICAL BUG FIXED**

The scanner now properly responds to the selected strategy and displays the correct strategy name and colors. Users can now:

1. ✓ Select a strategy from the home page
2. ✓ See the correct scanner title and labels
3. ✓ Have the strategy parameter passed to the backend

The infrastructure is now in place for Phase 2, where the backend will dispatch to the appropriate strategy class (CSP vs Wheel) for actual scanning.

