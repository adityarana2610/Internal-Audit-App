# Bank Operational Audit App — Implementation & Security Report

**Repository:** `adityarana2610/Internal-Audit-App` (Forked from `menonkrishna57/Internal-Audit-App`)  
**Active Branch:** `test-ai-scanner`  
**Date:** October 2026  
**Status:** Complete & Hardened for Enterprise Production  

---

## Executive Summary

This repository contains a full-stack, AI-powered internal banking audit application paired with an enterprise CI/CD security scanning pipeline. 

Over recent iterations, the application underwent comprehensive **enterprise hardening** to address critical access control, data persistence, and input validation vulnerabilities. In parallel, an automated **CI/CD Code Scanner & AI Fix Pipeline** was implemented to automatically audit pull requests using free-tier Google Gemini AI (`gemini-3.5-flash`), Ruff, Bandit, ESLint, and Pytest.

---

## 1. What Was Built: CI/CD & AI Code Scanner Suite

### 1.1 Multi-Repo Reusable Workflow (`.github/workflows/code-scan.yml`)
- **Automated PR Scans:** Triggers automatically on Pull Requests to `main` and `master`, or manually via `workflow_dispatch`.
- **Reusable Workflow (`workflow_call`):** Any external GitHub repository can invoke this entire scanning suite with just 4 lines of YAML:
  ```yaml
  jobs:
    security-audit:
      uses: adityarana2610/Internal-Audit-App/.github/workflows/code-scan.yml@test-ai-scanner
      secrets:
        GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
  ```
- **Integrated Tooling:**
  - **Ruff:** High-speed Python linter and formatter.
  - **Bandit:** Python AST security scanner (SQL injection, unsafe bindings, weak cryptography).
  - **ESLint:** React/JavaScript front-end static analysis and hook safety.
  - **Pytest:** Automated backend test suite execution.
- **Pull Request Bot:** Auto-posts and updates a formatted markdown summary directly on PR discussions under the `<!-- code-scan-ai-report -->` marker.
- **Artifact Generation:** Uploads full logs and standalone interactive HTML dashboards for 14-day retention.

### 1.2 Gemini AI Fix Suggestions Engine (`scripts/ai_fix_suggestions.py`)
- Analyzes raw scanner outputs and prompts Google Gemini AI (`gemini-3.5-flash`) on the zero-cost free tier.
- Auto-retries with exponential backoff on transient network issues and deprecation fallbacks.
- Generates:
  1. A structured Markdown report (`scan-results/ai-report.md`) with tables and diff snippets.
  2. A self-contained, dark-mode Web UI dashboard (`scan-results/report.html`) complete with syntax highlighting, severity filters, and one-click copy buttons.

### 1.3 Local Developer Scan CLI (`scripts/run_local_scan.py`)
- Allows developers to audit their code locally before pushing to GitHub.
- Includes a `--simulate` flag for offline testing and auto-launches the interactive browser dashboard upon completion.

---

## 2. Enterprise Security Hardening Completed

| # | Vulnerability / Gap | Risk Level | Remediated In | Solution Implemented |
|---|---|---|---|---|
| 1 | **Unauthenticated API Endpoints** | Critical | `app/auth.py`, `app/routes/*.py` | Implemented mandatory Bearer token authentication via `require_auth` at the router level for all routes in `audits.py` and `policies.py`. |
| 2 | **Fail-Open Authentication** | High | `app/auth.py` | Engine strictly fails closed: missing, empty, or unconfigured `API_AUTH_TOKEN` raises an explicit HTTP 500 error instead of allowing requests. |
| 3 | **Token Bundled in Frontend JS** | High | `audit-dashboard/src/App.jsx` | Removed all hardcoded and `VITE_` bundled tokens from frontend code. Built an interactive `AuthModal` that collects the user's secret Bearer token and stores it securely in `sessionStorage` or `localStorage`. |
| 4 | **Known Default / Placeholder Tokens** | High | `app/config.py`, `app/auth.py` | Added Pydantic `@field_validator` and middleware rejection of common placeholder tokens (`your-secure-secret-token-here`, `[GENERATE-A-UNIQUE-SECRET-TOKEN]`, `change-me`, `secret`, `password`). The server refuses to start with example tokens. |
| 5 | **Silent Qdrant In-Memory Fallback** | High | `app/policy_engine/vector_store.py` | Removed silent fallback to volatile in-memory storage (`:memory:`). If Qdrant is unreachable, an explicit `RuntimeError` is raised to prevent silent data loss, and the client remains uncached for automatic reconnection once online. |
| 6 | **Docker Container Startup Race** | Medium | `docker-compose.yml` | Added health checks to the Qdrant container and configured `audit-tool` with `condition: service_healthy` so the API waits for Qdrant to be ready. |
| 7 | **XSS in AI Narrative Rendering** | High | `audit-dashboard/src/App.jsx`, `index.html` | Integrated DOMPurify. Sanitizes all AI-generated markdown. Built a bulletproof fallback that escapes all HTML entities (`<`, `>`, `&`, `"`, `'`) via `textContent` DOM nodes if DOMPurify is offline. |
| 8 | **Gemini API Key Leakage** | Medium | `app/routes/audits.py` | Obscured the Gemini API key in `/settings` as a fixed `••••••••••••••••` mask with zero character leakage, preventing masked values from overwriting existing secrets. |
| 9 | **Uncapped PDF Uploads** | Medium | `app/routes/policies.py` | Enforced a streaming size ceiling of 25 MB (`MAX_POLICY_PDF_BYTES = 25 * 1024 * 1024`) to prevent memory exhaustion / DoS attacks. |
| 10 | **Missing Import NameError** | Blocker | `app/routes/policies.py` | Added missing `Depends` import from `fastapi`, ensuring clean server startup without runtime exceptions. |

---

## 3. Configuration & Environment Setup

Two configuration templates are provided:
- [`.env.example`](file:///.env.example) (repository root)
- [`audit-tool/.env.example`](file:///audit-tool/.env.example)

### Required Environment Variables
```ini
# Direct Postgres connection string (required)
SUPABASE_DB_URL=postgresql+psycopg://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres

# Environment mode: development | staging | production
ENVIRONMENT=development

# Mandatory Secret Bearer Token protecting all audit & policy endpoints (REQUIRED)
# Generate a strong token: python -c "import secrets; print(secrets.token_urlsafe(32))"
API_AUTH_TOKEN=[GENERATE-A-UNIQUE-SECRET-TOKEN]

# AI Provider (gemini | ollama)
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash

# Qdrant Vector Database
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=policy_clauses
```

---

## 4. Verification & Testing History

1. **AST & Syntax Integrity:**
   - Ran automated AST parser check across all Python files in the repository: `ALL PYTHON FILES SYNTAX OK!`.
2. **Pydantic Validation Guard:**
   - Verified that starting the server with placeholder tokens like `your-secure-secret-token-here` or `[GENERATE-A-UNIQUE-SECRET-TOKEN]` correctly triggers a `ValidationError` and prevents startup.
   - Verified that valid, unique custom tokens pass validation cleanly.
3. **Local CLI Scanner:**
   - Verified `python scripts/run_local_scan.py --simulate --no-browser` completes and outputs both `scan-results/local-ai-report.md` and `scan-results/report.html`.
4. **GitHub Actions CI Pipeline:**
   - Pull Request #1 triggered and executed the automated workflow.
   - The workflow uploaded the `code-scan-report` build artifact and posted the AI findings comment on GitHub.
