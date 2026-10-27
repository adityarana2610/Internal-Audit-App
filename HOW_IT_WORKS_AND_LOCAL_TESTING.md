# 🛠️ CI/CD Code Scanner & AI Fix Pipeline: Complete Guide & Local Testing

This document explains **how the system works**, **how you can test it locally on your computer right now**, and **how any repository can use it as a reusable workflow (Option B)**.

---

## 1. How It Works (The Full Picture)

Whenever a developer opens a Pull Request or pushes code:

```
[ Developer Opens PR ]
         │
         ▼
[ GitHub Actions Runner Boots Up (Ubuntu) ]
         │
         ├─► 1. Runs Ruff (Python linting: style, unused imports, logic errors)
         ├─► 2. Runs Bandit (Python security: SQL injections, hardcoded keys)
         ├─► 3. Runs ESLint (JavaScript/React: syntax, bad hooks, unused vars)
         └─► 4. Runs Pytest (Unit tests: verify functionality)
         │
         ▼
[ scripts/ai_fix_suggestions.py ]
         │
         ├─► Collects all scanner output logs
         ├─► Sends errors to Google Gemini API (2.0 Flash)
         └─► Assembles Markdown report:
               • Summary Table with pass/fail badges
               • Raw logs (collapsible)
               • AI-Generated Explanations & Exact Code Fixes
         │
         ▼
[ Posts / Updates PR Comment ]
  (Uses HTML marker <!-- code-scan-ai-report --> so subsequent pushes 
   update the existing comment instead of creating spam)
         │
         ▼
[ Quality Gate Evaluation ]
  (Fails CI if critical errors are present, passes if clean)
```

---

## 2. Test It Locally (Before Pushing Anything to GitHub!)

You don't need to wait for GitHub Actions to see this in action. A local test runner is ready and includes an **interactive Web UI**!

### Test Option A: Simulated Run (Instant Web UI Demo)
This injects sample Python, Security, and React errors into the scanner, generates the report, and **automatically launches an interactive Web UI dashboard in your web browser**:

```bash
# In your terminal (from project root):
python scripts/run_local_scan.py --simulate
```

**If you have a Gemini API key:**
```bash
# Pass your key to get live AI fix suggestions:
python scripts/run_local_scan.py --simulate --key YOUR_GEMINI_API_KEY
```

👉 **What Happens:**
1. Your default web browser will automatically open with a visual dark-mode dashboard.
2. You will see:
   - **KPI Metric Cards**: Total Issues, Security Flaws (Bandit), Python Lints (Ruff), JavaScript Bugs (ESLint).
   - **Interactive Filter Tabs**: Toggle between AI Fix Suggestions and Raw Logs.
   - **One-Click Copy Fix Buttons**: Click to copy the suggested replacement code directly to your clipboard.
3. The report is saved locally at both:
   - **Interactive Web UI:** `scan-results/report.html`
   - **GitHub Markdown:** `scan-results/local-ai-report.md`

*(Note: If you don't want the browser to pop up automatically, pass `--no-browser`)*

---

### Test Option B: Real Local Scan (Your Actual Code)
To scan your actual project code locally and view the web report:

1. **Install scanning tools:**
   ```bash
   pip install ruff bandit pytest
   ```

2. **Run the local scanner:**
   ```bash
   python scripts/run_local_scan.py
   ```
   *(Or with your key: `python scripts/run_local_scan.py --key YOUR_KEY`)*

Your browser will automatically open showing any real issues found in your project.


---

## 3. How to Enable It in THIS Repository

### Step 1: Add your Gemini API Key to GitHub
1. Go to your GitHub repository in your browser.
2. Click **Settings** (top right tab).
3. On the left sidebar, click **Secrets and variables** → **Actions**.
4. Click **New repository secret**.
5. Name: `GEMINI_API_KEY`
6. Value: Paste your Google Gemini API key.
7. Click **Add secret**.

### Step 2: Push the new CI/CD files
```bash
git add .github/workflows/code-scan.yml
git add scripts/ai_fix_suggestions.py
git add scripts/run_local_scan.py
git add .ruff.toml
git add requirements-dev.txt
git commit -m "feat: reusable CI/CD code scanner with AI fix suggestions"
git push origin main
```

### Step 3: Verify with a PR
1. Create a new test branch:
   ```bash
   git checkout -b test/ci-scanner-demo
   ```
2. Make a deliberate test error (e.g., add `import os` to `audit-tool/app/engine.py` without using it).
3. Commit and push:
   ```bash
   git commit -am "test: trigger scanner"
   git push origin test/ci-scanner-demo
   ```
4. Open a Pull Request on GitHub.
5. Within ~90 seconds, you will see a bot comment on the PR detailing the error and suggesting the fix!

---

## 4. How OTHER Repositories Can Use It (Option B: Reusable Workflow)

Because `.github/workflows/code-scan.yml` defines `workflow_call`, **any other GitHub repository can reuse this entire scanning & AI fix engine** by creating a single 10-line file.

### Example 1: Full Stack App (Python + React)
In the other repository, create `.github/workflows/scan.yml`:

```yaml
name: "Code Scan"
on:
  pull_request:
    branches: [main, master]

jobs:
  run-security-scan:
    uses: YOUR_GITHUB_USERNAME/Internal-Audit-App/.github/workflows/code-scan.yml@main
    secrets:
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
    with:
      scan_python: true
      scan_javascript: true
      python_dir: "backend"
      javascript_dir: "frontend"
```

### Example 2: Python-Only Repository
If another project only has Python code in the repository root:

```yaml
name: "Code Scan"
on:
  pull_request:
    branches: [main, master]

jobs:
  run-security-scan:
    uses: YOUR_GITHUB_USERNAME/Internal-Audit-App/.github/workflows/code-scan.yml@main
    secrets:
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
    with:
      scan_python: true
      scan_javascript: false
      python_dir: "."
      run_tests: true
```

### Example 3: JavaScript / Node.js Only Repository
If another project is purely frontend / React / Next.js:

```yaml
name: "Code Scan"
on:
  pull_request:
    branches: [main, master]

jobs:
  run-security-scan:
    uses: YOUR_GITHUB_USERNAME/Internal-Audit-App/.github/workflows/code-scan.yml@main
    secrets:
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
    with:
      scan_python: false
      scan_javascript: true
      javascript_dir: "."
```

---

## 5. Summary of Files in This Solution

| File | Role |
|---|---|
| [`.github/workflows/code-scan.yml`](file:///e:/InternalAuditApp/Internal-Audit-App/.github/workflows/code-scan.yml) | Reusable GitHub Actions workflow (runs linters, tests, and posts PR comment). |
| [`scripts/ai_fix_suggestions.py`](file:///e:/InternalAuditApp/Internal-Audit-App/scripts/ai_fix_suggestions.py) | Engine that consumes scanner logs, prompts Gemini, and produces both GitHub Markdown and interactive HTML Web UI reports. |
| [`scripts/run_local_scan.py`](file:///e:/InternalAuditApp/Internal-Audit-App/scripts/run_local_scan.py) | Local tester tool to test scanning and AI fix suggestions on your computer (auto-opens the Web UI in your browser). |

| [`.ruff.toml`](file:///e:/InternalAuditApp/Internal-Audit-App/.ruff.toml) | Python linter configuration rules. |
| [`audit-dashboard/.eslintrc.json`](file:///e:/InternalAuditApp/Internal-Audit-App/audit-dashboard/.eslintrc.json) | JavaScript / React linter rules. |
| [`requirements-dev.txt`](file:///e:/InternalAuditApp/Internal-Audit-App/requirements-dev.txt) | Dev tools (`ruff`, `bandit`, `pytest`, `httpx`). |
