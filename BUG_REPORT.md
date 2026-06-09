# CSP Scanner Website - Critical Bug Report

**Date:** 2026-06-08  
**Tester:** Critical Website Tester & Trading Expert  
**Severity Level:** Critical to Medium

---

## CRITICAL BUGS

### 🔴 **BUG #1: Port Mismatch Error - Wrong Port Configuration**
**Severity:** CRITICAL 🔴  
**Status:** BLOCKING PRODUCTION

**Issue:**
- Website serves on `http://localhost:5000`
- JavaScript is attempting to connect to `http://localhost:5001` for API calls
- **Evidence:** 15+ network failures showing `GET http://localhost:5001/api/alpaca/account → 502 BAD GATEWAY`

**Location:** 
- [web/static/js/dashboard.js](web/static/js/dashboard.js) - All fetch() calls need verification
- [web/app.py](web/app.py:24) - Flask app config or route handling

**Impact:**
- ❌ Alpaca account integration completely broken
- ❌ Users see repeated "Alpaca: {"message": "unauthorized."}" errors
- ❌ Account panel fails to load
- ❌ Trade execution buttons non-functional
- ❌ Positions & Orders tabs unreachable

**Reproduction:**
1. Open http://localhost:5000
2. Check browser DevTools Network tab
3. See repeated 502 errors to port 5001

**Required Fix:**
Ensure all API endpoints use correct port. Check:
- Base URL in dashboard.js (likely hardcoded to 5001)
- Flask app is listening on consistent port
- Environment variables or config files controlling port

---

### 🔴 **BUG #2: Dashboard.js Click Handler Selector Not Working**
**Severity:** CRITICAL 🔴  
**Status:** BLOCKING UI INTERACTION

**Issue:**
- "Run Scan" button cannot be clicked via CSS selector `button:contains("Run Scan")`
- Button exists in DOM but selector fails
- Indicates potential selector format incompatibility or DOM structure issue

**Location:** 
- [web/templates/index.html:138](web/templates/index.html:138) - `id="run-scan-btn"`
- [web/static/js/dashboard.js:68](web/static/js/dashboard.js:68) - Event listener binding

**Evidence:**
```
Failed to click element: button:contains("Run Scan")
```

**Impact:**
- ❌ Scan functionality might not trigger properly
- ❌ Click handlers could be non-functional
- ⚠️ User cannot initiate scans via button click

**Solution:**
Use `#run-scan-btn` ID selector or `button[id="run-scan-btn"]` instead of text-based selectors.

---

## HIGH PRIORITY BUGS

### 🟠 **BUG #3: Alpaca Account API Endpoint Hardcoded to Wrong Port**
**Severity:** HIGH 🟠

**Issue:**
- JavaScript sends requests to `http://localhost:5001/api/alpaca/account`
- Flask serves on port 5000
- Multiple retries creating network congestion

**Location:**
- [web/static/js/dashboard.js:799](web/static/js/dashboard.js:799) - `fetch("/api/alpaca/account", ...)`
- [web/static/js/dashboard.js:813](web/static/js/dashboard.js:813)
- [web/static/js/dashboard.js:851](web/static/js/dashboard.js:851)

**Evidence:**
```json
15× GET http://localhost:5001/api/alpaca/account → 502 BAD GATEWAY
```

**Fix Required:**
- Remove hardcoded port from fetch URLs
- Use relative paths: `/api/alpaca/account` instead of full URLs
- OR verify Flask is configured to listen on port 5001

---

### 🟠 **BUG #4: Error Banner Shows Raw JSON Object**
**Severity:** HIGH 🟠  
**Status:** POOR UX

**Issue:**
- Error message displays as: `Alpaca: {"message": "unauthorized."}`
- Shows raw API response instead of user-friendly message
- Users see technical JSON instead of actionable error

**Location:**
- [web/static/js/dashboard.js:801](web/static/js/dashboard.js:801) - Error handling in `loadAlpacaAccount()`

**Evidence:**
Alert shows: `Alpaca: {"message": "unauthorized."}`

**Current Code:**
```javascript
if (d.error) { showError("Alpaca: " + d.error); return; }
```

**Fix Required:**
Parse JSON error object and extract message:
```javascript
const msg = typeof d.error === 'string' ? d.error : (d.error?.message || 'Unknown error');
showError("Alpaca: " + msg);
```

---

### 🟠 **BUG #5: Missing Alpaca Panel in Offline Mode**
**Severity:** HIGH 🟠

**Issue:**
- Alpaca panel shows confusing error message instead of setup instructions
- Users see `Alpaca: {"message": "unauthorized."}` but don't know how to fix it
- CTA "Set up credentials" button not visible/clickable in error state

**Location:**
- [web/templates/index.html:146-157](web/templates/index.html:146-157) - Alpaca panel markup
- [web/static/js/dashboard.js:792-806](web/static/js/dashboard.js:792-806) - Panel rendering logic

**Impact:**
- Users cannot connect Alpaca account
- No clear path to set up credentials
- Breaks the "Sign up → Configure → Trade" workflow

---

## MEDIUM PRIORITY BUGS

### 🟡 **BUG #6: Table Column Colspan Mismatch**
**Severity:** MEDIUM 🟡

**Issue:**
- Table uses hardcoded `colspan="9"` but Trade column (10th column) not counted
- If Alpaca is connected, becomes 10 columns but colspan stays 9
- Expansion row may not span full width when Trade column visible

**Location:**
- [web/templates/index.html:335](web/templates/index.html:335) - Empty state: `colspan="9"`
- [web/static/js/dashboard.js:381](web/static/js/dashboard.js:381) - Comment mentions COLSPAN = 15 (mismatch!)

**Evidence:**
```javascript
// C3: always use full colspan (15+1 for trade col when connected)
const COLSPAN = 15;  // ← But only 10 columns exist!
```

**Impact:**
- ⚠️ Expansion rows may not align with table layout
- Empty state message doesn't span correctly
- Cosmetic but indicates code confusion

---

### 🟡 **BUG #7: DTE Custom Input Validation Missing**
**Severity:** MEDIUM 🟡

**Issue:**
- Custom DTE inputs allow any value without validation
- User can enter invalid ranges: min=730, max=1 (backwards)
- Code checks `if (min > max)` but only in startScan(), not on input

**Location:**
- [web/templates/index.html:117-120](web/templates/index.html:117-120) - Inputs have no `min`/`max` constraints
- [web/static/js/dashboard.js:78-81](web/static/js/dashboard.js:78-81) - Validation happens too late

**Evidence:**
```javascript
if (min > max) {
  showError("Min DTE must be less than Max DTE.");
  return;  // Only when scanning, not on input
}
```

**Fix Required:**
```html
<input id="dte-min-input" type="number" min="1" max="730" value="1">
<input id="dte-max-input" type="number" min="1" max="730" value="730">
```

Add runtime validation on blur:
```javascript
[$("dte-min-input"), $("dte-max-input")].forEach(inp => {
  inp.addEventListener("blur", () => {
    const min = parseInt($("dte-min-input").value) || 1;
    const max = parseInt($("dte-max-input").value) || 730;
    if (min > max) {
      showError("Min DTE must be less than Max DTE.");
      $("dte-min-input").value = max;
    }
  });
});
```

---

### 🟡 **BUG #8: Filter State Not Synced on Tab Switch**
**Severity:** MEDIUM 🟡

**Issue:**
- Switching tabs clears visual sort indicators (correct)
- But filters remain applied from previous tab
- User expects each tab to have fresh filtering state

**Location:**
- [web/static/js/dashboard.js:262-266](web/static/js/dashboard.js:262-266) - Tab filter logic
- [web/static/js/dashboard.js:1090-1129](web/static/js/dashboard.js:1090-1129) - Tab click handler

**Evidence:**
```javascript
// H6: clear sort indicators when tab overrides sort
if (tab !== "all") {
  document.querySelectorAll("#results-table th").forEach(h =>
    h.classList.remove("sort-asc", "sort-desc")
  );  // Clears sort, but sidebar filters persist!
}
```

**Impact:**
- User filters GOOG on "All" tab, switches to "Safest" tab
- Sees results filtered to only GOOG, confusing
- Expected: Fresh "Safest" results, unfiltered

---

### 🟡 **BUG #9: Mini Chart Container May Overflow on Small Screens**
**Severity:** MEDIUM 🟡

**Issue:**
- Expansion card contains canvas chart with no height constraint
- On mobile/tablet, chart may overflow or squash
- CSS doesn't specify container dimensions

**Location:**
- [web/static/js/dashboard.js:422](web/static/js/dashboard.js:422) - `createMiniChartHtml()` returns bare canvas
- [web/static/js/dashboard.js:499-532](web/static/js/dashboard.js:499-532) - Chart initialization with `maintainAspectRatio: false`
- [web/templates/index.html:420-423](web/templates/index.html:420-423) - No CSS constraints

**Fix Required:**
Add CSS or inline styles:
```html
<div class="expansion-chart-container" style="height: 200px; width: 100%; max-width: 400px;">
  <canvas id="chart-..."></canvas>
</div>
```

---

## LOW PRIORITY BUGS / WARNINGS

### 🔵 **BUG #10: Infinite Retry Loop on Connection Failure**
**Severity:** LOW 🔵  
**Status:** Inefficient Resource Usage

**Issue:**
- `pollScanStatus()` retries every 2 seconds indefinitely on failure
- If server goes down mid-scan, retry loop never stops
- Can cause high CPU/network usage

**Location:**
- [web/static/js/dashboard.js:107-134](web/static/js/dashboard.js:107-134)

**Current Code:**
```javascript
scanPollTimer = setInterval(() => {
  // ... poll status ...
}, 2000);  // Runs forever if fetch fails silently
```

**Evidence:**
Line 132: `.catch(() => {});` - Silently ignores network errors

**Fix Required:**
Add max retry count:
```javascript
let pollRetries = 0;
const MAX_RETRIES = 30; // 60 seconds max
scanPollTimer = setInterval(() => {
  pollRetries++;
  if (pollRetries > MAX_RETRIES) {
    clearInterval(scanPollTimer);
    showError("Scan timeout after 60 seconds. Please try again.");
    return;
  }
  // ... rest of polling ...
}, 2000);
```

---

### 🔵 **BUG #11: Scan History Dropdown Shows Wrong Label on Load**
**Severity:** LOW 🔵

**Issue:**
- History dropdown initially shows "Loading…" but never updates if empty
- If no scan history exists, dropdown stays broken

**Location:**
- [web/templates/index.html:29-31](web/templates/index.html:29-31)
- [web/static/js/dashboard.js:165-177](web/static/js/dashboard.js:165-177)

**Current Code:**
```javascript
.catch(() => {
  $("scan-history").innerHTML = `<option value="">Error loading history</option>`;
});
```

**Impact:**
- User sees "Error loading history" even if no scans exist yet
- Should show helpful message: "No previous scans"

---

### 🔵 **BUG #12: Tech Score Formatting Inconsistent**
**Severity:** LOW 🔵  
**Status:** Minor Display Issue

**Issue:**
- Tech score displays as "54/100" in row data
- But shows "54" in banded picks with "100" in label
- Inconsistent format confuses users

**Location:**
- [web/static/js/dashboard.js:365](web/static/js/dashboard.js:365) - `${r.tech_score + "/100"}`
- [web/static/js/dashboard.js:473-475](web/static/js/dashboard.js:473-475) - Different format

**Fix:** Standardize to always show: `${r.tech_score}/100`

---

### 🔵 **BUG #13: Numeric Precision Issues in Float Display**
**Severity:** LOW 🔵

**Issue:**
- Bid-ask spread shows: `0.029411764705882377`
- Premium shows: `5.850000000000000`
- Floating-point artifacts visible to users

**Location:**
- All numeric fields need `.toFixed(2)` or `.toFixed(4)` formatting

**Evidence from API response:**
```json
"bid_ask_spread_pct": 0.029411764705882377,
"premium": 5.85
```

**Fix:**
Format all monetary values in dashboard.js using `fmt2()` or `fmt1()` helper functions already available.

---

### 🔵 **BUG #14: No Loading Skeleton During Table Render**
**Severity:** LOW 🔵  
**Status:** UX Improvement Needed

**Issue:**
- Results table shows empty state briefly before populating
- User sees flash of "Configure your scan" → actual results
- No skeleton loader or transition animation

**Impact:**
- Feels janky/broken even though it works
- Users might click again thinking page didn't load

---

## SUMMARY TABLE

| Bug # | Title | Severity | Type | Status |
|-------|-------|----------|------|--------|
| 1 | Port Mismatch (5000 vs 5001) | CRITICAL | Config/Network | BLOCKING |
| 2 | Run Scan Button Selector Broken | CRITICAL | JavaScript | BLOCKING |
| 3 | Alpaca API Hardcoded Port | HIGH | Network | BLOCKING |
| 4 | Raw JSON in Error Banner | HIGH | UX | Easy Fix |
| 5 | Missing Alpaca Setup Panel | HIGH | UX | Moderate |
| 6 | Table Colspan Mismatch | MEDIUM | Layout | Cosmetic |
| 7 | DTE Input Validation Missing | MEDIUM | Validation | Easy Fix |
| 8 | Filter State Persists on Tab Switch | MEDIUM | Logic | Easy Fix |
| 9 | Mini Chart Overflow on Mobile | MEDIUM | CSS/Responsive | Easy Fix |
| 10 | Infinite Retry Loop | LOW | Performance | Moderate |
| 11 | History Dropdown Error Message | LOW | UX | Easy Fix |
| 12 | Tech Score Format Inconsistent | LOW | Display | Trivial |
| 13 | Float Precision in Display | LOW | Display | Easy Fix |
| 14 | No Loading Skeleton | LOW | UX/Polish | Enhancement |

---

## RECOMMENDED FIX PRIORITY

### Phase 1 - CRITICAL (Do First)
1. **Fix port mismatch** - Blocking all Alpaca features
2. **Fix Run Scan selector** - Blocking core functionality

### Phase 2 - HIGH (Next Sprint)
3. Fix Alpaca API endpoint configuration
4. Improve error message formatting
5. Implement proper Alpaca setup flow

### Phase 3 - MEDIUM (Follow-up)
6. Add DTE input validation
7. Fix filter persistence on tab switch
8. Test responsive design for charts

### Phase 4 - LOW (Polish)
9. Add retry limits to polling
10. Improve error messages
11. Add loading skeletons

---

## TESTING CHECKLIST

- [ ] Verify Flask app running on correct port
- [ ] Test Alpaca account connection end-to-end
- [ ] Run scan with valid parameters
- [ ] Switch between tabs without clearing sidebar filters
- [ ] Test on mobile/tablet viewport
- [ ] Test with no previous scan history
- [ ] Verify all numeric formatting
- [ ] Check browser console for JS errors
- [ ] Test network error handling
- [ ] Verify all buttons are clickable

---

**Total Bugs Found:** 14  
**Critical Bugs:** 2  
**High Priority:** 3  
**Medium Priority:** 4  
**Low Priority:** 5

