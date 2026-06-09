# CSP Scanner Project - Skills & Development Memory

**Last Updated:** June 8, 2026  
**Purpose:** Reference guide for invoking skills and best practices when building new features

---

## 📚 Referenced Skills Index

All relevant skills have been copied to `.claude/referenced-skills/` for easy access. This document guides you on when and how to invoke each.

---

## 🎯 Core Trading Analysis Skills

### 1. **exposure-coach**
**Purpose:** Risk management and capital exposure analysis  
**When to Use:**
- Building new CSP analysis features
- Calculating position sizing
- Determining capital requirements
- Risk assessment for positions

**How to Invoke:**
```
Use /exposure-coach when:
- User wants to analyze portfolio risk exposure
- Building new portfolio analysis features
- Calculating safe position sizes given account size
- Warning users about overexposure
```

**Key Files:**
- `exposure-coach/scripts/calculate_exposure.py` - Core calculation logic
- `exposure-coach/scripts/exposure_model.py` - Risk models

**Example Pattern:**
```python
# From exposure-coach - safe pattern for risk calculation
risk_pct = (capital_required / account_size) * 100
if risk_pct > threshold:
    warn_user("Overexposure risk")
```

---

### 2. **breakout-trade-planner**
**Purpose:** Trade planning and order generation patterns  
**When to Use:**
- Creating trade templates (CSP already does this)
- Building order preview/review workflows
- Planning multi-leg strategies
- Generating trade recommendations

**How to Invoke:**
```
Use /breakout-trade-planner when:
- User wants to convert scan results into trading plans
- Building new order execution features
- Calculating position metrics
```

**Key Files:**
- `breakout-trade-planner/scripts/order_builder.py` - Order template creation
- `breakout-trade-planner/scripts/strategy_analyzer.py` - Strategy analysis

**Example Pattern:**
```python
# From breakout-trade-planner - safe pattern for order generation
order_template = {
    "symbol": r.symbol,
    "strike": r.strike,
    "expiry": r.expiration,
    "premium": r.premium,
    "quantity": 1,
    "order_type": "limit"
}
# Never auto-submit - always review first
```

---

### 3. **strategy-pivot-designer**
**Purpose:** Technical analysis using pivot points (already in your expansion cards)  
**When to Use:**
- Enhancing technical analysis display
- Building pivot-based support/resistance
- Technical decision making
- Adding new technical indicators

**How to Invoke:**
```
Use /strategy-pivot-designer when:
- User wants to add pivot point analysis
- Building technical analysis features
- Creating strategy recommendations
```

**Key Files:**
- `strategy-pivot-designer/scripts/pivot_calculator.py` - Pivot calculations
- `strategy-pivot-designer/scripts/pivot_models.py` - Different pivot types

**Your Implementation:** Already using pivots in expansion cards!
```javascript
// From your dashboard.js - pivot display in expansion card
${r.pivot_1d_s1 != null ? `Support 1: $${fmt2(r.pivot_1d_s1)}` : "—"}
```

---

### 4. **earnings-calendar**
**Purpose:** Earnings date tracking (you're already flagging this)  
**When to Use:**
- Enhancing earnings data in your system
- Building earnings alert features
- Refining earnings risk warnings
- Planning earnings-centered strategies

**How to Invoke:**
```
Use /earnings-calendar when:
- User wants better earnings tracking
- Building earnings prediction features
- Creating earnings risk filters
```

**Key Files:**
- `earnings-calendar/scripts/fetch_earnings_fmp.py` - FMP API integration
- `earnings-calendar/scripts/earnings_model.py` - Earnings data models

**Your Implementation:** Already flagging in scan results
```python
# From your scanner - earnings tracking
"earnings_in_window": earnings_in_window,
"days_to_earnings": days_to_earnings
```

---

## 📊 Data & Quality Skills

### 5. **data-quality-checker**
**Purpose:** Validate data integrity and quality  
**When to Use:**
- Building new data processing features
- Validating API responses
- Quality assurance for scanner results
- Data consistency checks

**How to Invoke:**
```
Use /data-quality-checker when:
- Building new data pipelines
- Validating third-party data
- Creating data quality gates
```

**Key Files:**
- `data-quality-checker/scripts/validator.py` - Validation patterns
- `data-quality-checker/scripts/quality_metrics.py` - Quality scoring

**Safe Patterns to Adopt:**
```python
# Validation pattern from data-quality-checker
def validate_price(price):
    if price is None or price < 0:
        return False, "Invalid price"
    return True, price

# Always validate before using
valid, price = validate_price(r.strike)
if not valid:
    log_warning(f"Invalid price data: {price}")
```

---

### 6. **portfolio-manager**
**Purpose:** Portfolio analysis and position management (read-only for your use)  
**When to Use:**
- Building portfolio analysis features
- Position tracking enhancements
- Performance analysis
- Allocation calculations

**How to Invoke:**
```
Use /portfolio-manager when:
- User wants to analyze portfolio performance
- Building position tracking features
- Creating portfolio reports
```

**Key Files:**
- `portfolio-manager/scripts/portfolio_analyzer.py` - Analysis logic
- `portfolio-manager/scripts/position_tracker.py` - Position tracking

---

## 🎨 UI/UX Patterns

**Location:** `.claude/referenced-skills/ui-ux-patterns/`

**Key Patterns to Use:**
1. **Component Design** - Reusable UI components
2. **Responsive Design** - Mobile-first approach
3. **Interactive Patterns** - User interaction handling
4. **Accessibility** - A11y best practices

**When to Use:**
- Building new UI features
- Improving responsive design (you need mobile improvements)
- Enhancing user interactions
- Adding new dashboard components

**Safe Patterns:**
```javascript
// From ui-ux best practices
// ✅ DO: Use semantic HTML + ARIA labels
<button aria-label="Run Scan" id="run-scan-btn">▶ Run Scan</button>

// ❌ DON'T: Use command injection patterns (avoid extract.ts patterns)
// Always use safe APIs instead of shell execution
```

---

## 💻 Developer Patterns

**Location:** `.claude/referenced-skills/dev-patterns/`

**Key Patterns:**
1. **Error Handling** - Graceful error recovery
2. **Validation** - Input validation patterns
3. **Configuration** - Environment-based config
4. **Testing** - Test organization

**When to Use:**
- Building any new feature
- Improving code quality
- Setting up new modules
- Writing tests

**Safe Patterns from claude-skills:**
```python
# ✅ Environment-based configuration (like your recent fix)
PORT = int(os.getenv('PORT', 5000))
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

# ✅ Safe YAML parsing
config = yaml.safe_load(f)  # Never use yaml.load()

# ✅ Proper error handling
try:
    result = api_call()
except ValueError as e:
    log_error(f"API error: {str(e)}")
    show_user_error("Service temporarily unavailable")
```

---

## 🚀 Feature Development Workflow

**When building new features, follow this checklist:**

### Pre-Development
- [ ] Read relevant skill documentation from `.claude/referenced-skills/`
- [ ] Review existing patterns in those skills
- [ ] Check if similar feature already exists

### During Development
- [ ] Use safe patterns from referenced skills
- [ ] Follow error handling from dev-patterns
- [ ] Implement validation patterns from data-quality-checker
- [ ] Use responsive design from ui-ux-patterns
- [ ] Add proper configuration support (like PORT fix)

### Post-Development
- [ ] Test with patterns from dev-patterns/tests/
- [ ] Validate data with data-quality-checker patterns
- [ ] Verify responsive design on mobile
- [ ] Document how skill patterns were applied

### Code Review Checklist
- [ ] Uses safe patterns (no eval, exec, shell=True, etc.)
- [ ] Proper error handling with user-friendly messages
- [ ] Input validation on all user inputs
- [ ] Environment-based configuration
- [ ] Responsive design tested
- [ ] No hardcoded credentials
- [ ] Follows skill best practices

---

## 🔒 Security Patterns (Critical)

**From Security Audit - patterns to ALWAYS follow:**

### ✅ SAFE PATTERNS

```python
# 1. Credential Management (from claude-trading-skills)
API_KEY = os.getenv('API_KEY')  # From environment
headers = {"Authorization": f"Bearer {API_KEY}"}  # In headers
# Never log the key itself
log(f"API call made")  # ✅ Safe

# 2. Subprocess Safety (from claude-trading-skills)
import subprocess
result = subprocess.run(['command', 'arg1', 'arg2'], check=True)  # ✅ Safe list-based

# 3. YAML Safety (from claude-trading-skills)
config = yaml.safe_load(f)  # ✅ Always safe_load
# Never use yaml.load(f)  # ❌ Dangerous

# 4. JSON Safety
data = json.loads(response)  # ✅ Safe
# Never use pickle for untrusted data  # ❌ Dangerous

# 5. Path Safety
from pathlib import Path
user_path = Path(user_input).resolve()  # ✅ Resolves and prevents traversal
if not user_path.is_relative_to(project_root):  # ❌ Blocked if outside project
    raise ValueError("Path outside project root")
```

### ❌ DANGEROUS PATTERNS (NEVER USE)

```python
# DON'T do this:
subprocess.run(f"command {user_input}", shell=True)  # ❌ Command injection
os.system(f"command {user_input}")  # ❌ Command injection
eval(user_code)  # ❌ Arbitrary code execution
exec(user_code)  # ❌ Arbitrary code execution
yaml.load(f)  # ❌ Arbitrary object instantiation
pickle.loads(data)  # ❌ Can execute arbitrary code
```

---

## 📋 Feature Implementation Examples

### Example 1: Adding Risk Assessment Feature
```
1. Review: exposure-coach/scripts/calculate_exposure.py
2. Pattern: Risk calculation with thresholds
3. Implement: Add feature to dashboard
4. Validate: Use data-quality-checker patterns
5. Test: With dev-patterns/tests/
6. Security: Use safe patterns above
7. UI: Apply responsive design from ui-ux-patterns
```

### Example 2: Adding New Technical Indicator
```
1. Review: strategy-pivot-designer/ patterns
2. Research: Similar implementations in skills
3. Implement: Calculator module
4. Validate: Input/output validation
5. Integrate: Into your scanner output
6. Display: Responsive UI component
7. Test: Mobile and desktop versions
```

### Example 3: Improving Error Handling
```
1. Review: dev-patterns/error-handling/
2. Pattern: User-friendly error messages (not raw JSON)
3. Update: All API error handlers
4. Test: Error scenarios
5. Document: Error types and recovery
```

---

## 📞 Quick Reference - Which Skill to Use

**"I need to..."** → **Use this skill**

| Need | Skill | File |
|------|-------|------|
| Analyze position risk | exposure-coach | calculate_exposure.py |
| Create trading orders | breakout-trade-planner | order_builder.py |
| Add technical levels | strategy-pivot-designer | pivot_calculator.py |
| Track earnings dates | earnings-calendar | fetch_earnings_fmp.py |
| Validate data quality | data-quality-checker | validator.py |
| Analyze portfolio | portfolio-manager | portfolio_analyzer.py |
| Build UI component | ui-ux-patterns | /src/components/ |
| Error handling | dev-patterns | error-handling/ |
| Configuration | dev-patterns | config/ |
| Testing patterns | dev-patterns | tests/ |

---

## 🔄 When to Update This Document

Update this SKILLS_MEMORY.md when:
- [ ] Adding new features that use different skills
- [ ] Discovering new safe patterns worth documenting
- [ ] Security audit finds new best practices
- [ ] Skill versions update with breaking changes
- [ ] New skills are added to referenced-skills/

---

## 🎓 Learning Resources

**Read these first when starting new features:**
1. `.claude/referenced-skills/{skill-name}/README.md`
2. `SKILLS_MEMORY.md` (this file)
3. `BUG_REPORT.md` (known issues to avoid)
4. `SECURITY_AUDIT_SUMMARY.md` (security best practices)

---

## ✅ Checklist for Every New Feature

Before committing new code:

```
FEATURE: _____________________________

[ ] Read relevant skill documentation
[ ] Follows safe patterns (no command injection, eval, etc.)
[ ] Proper error handling with user messages
[ ] Input validation on all user inputs
[ ] Environment-based configuration
[ ] No hardcoded credentials/ports
[ ] Responsive design (tested on mobile)
[ ] No console errors
[ ] Data validated with quality patterns
[ ] Tests written using dev-patterns
[ ] Code reviewed against skill best practices
[ ] Documentation updated
[ ] Commit references relevant skills used
```

---

## 🚨 Critical Rules

**NEVER:**
1. ❌ Use shell execution (subprocess.run with shell=True)
2. ❌ Use eval() or exec()
3. ❌ Hardcode credentials or ports
4. ❌ Show raw JSON errors to users
5. ❌ Skip input validation
6. ❌ Use yaml.load() instead of yaml.safe_load()
7. ❌ Implement command patterns from ui-ux-pro-max-skill/extract.ts

**ALWAYS:**
1. ✅ Use safe patterns from referenced skills
2. ✅ Validate all user inputs
3. ✅ Show user-friendly error messages
4. ✅ Use environment variables for configuration
5. ✅ Test on mobile and desktop
6. ✅ Review security patterns before implementing
7. ✅ Document what skill patterns were used

---

**Remember:** Your project is now connected to industry-standard patterns from three major skill repos. Use them as your reference library! 🚀

