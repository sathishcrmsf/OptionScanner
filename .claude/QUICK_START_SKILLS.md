# Quick Start: Using Skills in CSP Scanner Development

**TL;DR:** When building features, check `.claude/referenced-skills/` and `.claude/SKILLS_MEMORY.md`

---

## 🚀 5-Minute Setup

Your skills are ready at:
```
.claude/referenced-skills/
├── exposure-coach/              (Risk & capital management)
├── breakout-trade-planner/      (Trade planning patterns)
├── strategy-pivot-designer/     (Technical analysis)
├── earnings-calendar/           (Earnings tracking)
├── data-quality-checker/        (Data validation)
├── portfolio-manager/           (Portfolio analysis)
├── dev-patterns/                (Error handling, config, testing)
└── ui-ux-patterns/              (UI/UX best practices)
```

---

## 🎯 Start Here for Each Feature Type

### Adding Risk/Capital Analysis
```
1. Open: .claude/referenced-skills/exposure-coach/
2. Read: README.md
3. Check: scripts/calculate_exposure.py
4. Apply: Safe risk calculation patterns
5. Reference: SKILLS_MEMORY.md section "exposure-coach"
```

### Building Trade Planning UI
```
1. Open: .claude/referenced-skills/breakout-trade-planner/
2. Read: README.md
3. Check: scripts/order_builder.py
4. Apply: Safe order generation patterns
5. Reference: SKILLS_MEMORY.md section "breakout-trade-planner"
```

### Adding Technical Analysis
```
1. Open: .claude/referenced-skills/strategy-pivot-designer/
2. Read: README.md
3. Check: scripts/pivot_calculator.py
4. Apply: Pivot calculation patterns
5. Reference: SKILLS_MEMORY.md section "strategy-pivot-designer"
```

### Improving Data Quality
```
1. Open: .claude/referenced-skills/data-quality-checker/
2. Read: README.md
3. Check: scripts/validator.py
4. Apply: Validation patterns
5. Reference: SKILLS_MEMORY.md section "data-quality-checker"
```

### Building UI Components
```
1. Open: .claude/referenced-skills/ui-ux-patterns/
2. Review: Component structure
3. Check: Responsive design patterns
4. Apply: Best practices
5. Reference: SKILLS_MEMORY.md section "UI/UX Patterns"
```

### Writing Error Handling
```
1. Open: .claude/referenced-skills/dev-patterns/
2. Read: error-handling patterns
3. Check: Exception handling examples
4. Apply: User-friendly error messages
5. Reference: SKILLS_MEMORY.md section "Developer Patterns"
```

---

## ⚡ Common Tasks

### "How do I calculate position risk?"
→ Use `exposure-coach/scripts/calculate_exposure.py`
→ Pattern: Safe risk calculation with thresholds
→ See: SKILLS_MEMORY.md → "exposure-coach"

### "How do I generate trade orders safely?"
→ Use `breakout-trade-planner/scripts/order_builder.py`
→ Pattern: Template-based order (no auto-execution)
→ See: SKILLS_MEMORY.md → "breakout-trade-planner"

### "How do I validate data?"
→ Use `data-quality-checker/scripts/validator.py`
→ Pattern: Try-except with logging
→ See: SKILLS_MEMORY.md → "data-quality-checker"

### "How do I handle errors?"
→ Use `dev-patterns/error-handling/`
→ Pattern: User-friendly messages, proper logging
→ See: SKILLS_MEMORY.md → "Developer Patterns"

### "How do I make UI responsive?"
→ Use `ui-ux-patterns/src/`
→ Pattern: Mobile-first approach
→ See: SKILLS_MEMORY.md → "UI/UX Patterns"

---

## 🛡️ Security Quick Check

Before committing code, verify:

```
[ ] No subprocess.run(shell=True) - use list-based args
[ ] No eval() or exec()
[ ] No hardcoded credentials
[ ] No hardcoded ports - use os.getenv()
[ ] All user inputs validated
[ ] Errors shown as user-friendly messages
[ ] No raw JSON in error output
[ ] yaml.safe_load() not yaml.load()
[ ] Environment-based configuration
```

See: SKILLS_MEMORY.md → "Security Patterns"

---

## 📚 File Structure Reference

```
Trading/
├── .claude/
│   ├── SKILLS_MEMORY.md              ← Read this for detailed guide
│   ├── QUICK_START_SKILLS.md         ← You are here
│   ├── referenced-skills/             ← All skill implementations
│   │   ├── exposure-coach/
│   │   ├── breakout-trade-planner/
│   │   ├── strategy-pivot-designer/
│   │   ├── earnings-calendar/
│   │   ├── data-quality-checker/
│   │   ├── portfolio-manager/
│   │   ├── dev-patterns/
│   │   └── ui-ux-patterns/
│   └── plans/                         ← Implementation plans
├── BUG_REPORT.md                      ← Known issues
├── SECURITY_AUDIT_SUMMARY.md          ← Security best practices
├── web/                               ← Application code
├── scanner/                           ← Scanner logic
└── ...
```

---

## 🔗 When to Invoke Skills in New Features

### During Planning Phase
→ Reference skill patterns in your design
→ Check SKILLS_MEMORY.md for similar implementations

### During Implementation Phase
→ Copy safe code patterns from skills
→ Follow validation and error handling approaches
→ Use responsive design patterns

### During Code Review Phase
→ Verify compliance with skill best practices
→ Check security patterns section
→ Validate error handling and user messages

### During Testing Phase
→ Use test patterns from dev-patterns/
→ Apply data quality checks
→ Test responsive design on mobile

---

## 💬 How to Mention Skills in Commits

When you use skill patterns, mention them:

```git
feat: Add capital risk calculator

- Uses exposure-coach patterns for risk calculation
- Validates input with data-quality-checker approach
- Shows user-friendly error messages per dev-patterns
- Responsive design from ui-ux-patterns

Refs: .claude/referenced-skills/exposure-coach/
Refs: .claude/referenced-skills/data-quality-checker/
```

---

## ✅ New Feature Checklist

```
NEW FEATURE: ___________________

BEFORE YOU START:
[ ] Read SKILLS_MEMORY.md section on topic
[ ] Reviewed relevant skill in referenced-skills/
[ ] Checked for similar implementations

DURING DEVELOPMENT:
[ ] Using safe patterns from skills
[ ] Following error handling approach
[ ] Input validation implemented
[ ] User messages friendly (not raw JSON)
[ ] Environment-based configuration
[ ] Responsive design on mobile/desktop

BEFORE COMMITTING:
[ ] Security patterns verified
[ ] No console errors
[ ] Tests written (dev-patterns style)
[ ] Code follows skill best practices
[ ] Commit mentions which skills were used
[ ] SKILLS_MEMORY.md updated if needed
```

---

## 🚨 Red Flags - Don't Do These!

```
❌ subprocess.run(cmd, shell=True)
❌ eval(user_input)
❌ exec(user_code)
❌ PORT = 5001  # hardcoded
❌ API_KEY = "sk-xxx"  # hardcoded
❌ yaml.load(f)  # use yaml.safe_load()
❌ showError(d.error)  # raw JSON
❌ try: pass except: pass  # silent failures
```

See: SKILLS_MEMORY.md → "Security Patterns"

---

## 📞 Questions?

- **"Which skill should I use?"** → See "Common Tasks" above
- **"How do I implement this safely?"** → See SKILLS_MEMORY.md → "Security Patterns"
- **"What patterns exist for this?"** → Browse referenced-skills/ directory
- **"Is this a safe pattern?"** → Check SKILLS_MEMORY.md → "Safe Patterns"

---

## 🎓 Next Steps

1. ✅ You have all skills in `.claude/referenced-skills/`
2. ✅ You have SKILLS_MEMORY.md with detailed guidance
3. ✅ You have QUICK_START_SKILLS.md (this file)
4. 👉 **Next:** Read SKILLS_MEMORY.md when starting your next feature

Happy building! 🚀

