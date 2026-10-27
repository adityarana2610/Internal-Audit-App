#!/usr/bin/env python3
"""
ai_fix_suggestions.py — CI/CD & Local Scanner helper script.

Reads output from linters & scanners (Ruff, Bandit, ESLint, Pytest),
sends identified errors to the Gemini API, and outputs a formatted
Markdown report containing:
  1. A high-level status summary table
  2. Captured scanner outputs
  3. Actionable AI-generated explanations and code fixes

Can be run:
  - In GitHub Actions (auto-posts to PR)
  - Locally on your machine (to test before pushing)

Usage:
    python scripts/ai_fix_suggestions.py \
        --ruff scan-results/ruff.txt \
        --bandit scan-results/bandit.txt \
        --eslint scan-results/eslint.txt \
        --pytest scan-results/pytest.txt \
        --output scan-results/ai-report.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# API Key resolution (Env var -> .env files -> CLI arg)
# ---------------------------------------------------------------------------

def resolve_gemini_api_key(explicit_key: str | None = None) -> str:
    """Find Gemini API key from CLI flag, env, or local .env files."""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()

    env_val = os.getenv("GEMINI_API_KEY")
    if env_val and env_val.strip():
        return env_val.strip()

    # Check common .env locations if running locally
    candidate_paths = [
        Path(".env"),
        Path("audit-tool/.env"),
        Path("../.env"),
    ]
    for p in candidate_paths:
        if p.exists():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
            except Exception:
                pass

    return ""


# ---------------------------------------------------------------------------
# Gemini API helper
# ---------------------------------------------------------------------------

def call_gemini(prompt: str, api_key: str) -> tuple[str | None, str | None]:
    """
    Send prompt to Gemini API.
    Tries:
      1. Modern official google.genai SDK (recommended & free)
      2. google.generativeai SDK
      3. Raw REST fallback (v1 & v1beta endpoints)
    Returns (response_text, error_message).
    """
    import urllib.error
    import urllib.request

    clean_key = api_key.strip().strip("'").strip('"')

    # ── Method 1: Official google.genai SDK ──────────────────────────────────
    try:
        from google import genai
        client = genai.Client(api_key=clean_key)
        for m_name in ["gemini-3.8-flash", "gemini-2.5-flash"]:
            try:
                resp = client.models.generate_content(
                    model=m_name,
                    contents=prompt,
                )
                if resp and resp.text:
                    print(f"✅ Successfully generated fixes using google.genai ({m_name})")
                    return resp.text.strip(), None
            except Exception as e:
                err_s = str(e)
                if "API_KEY_INVALID" in err_s or "400" in err_s:
                    return None, f"Invalid API Key: {e}"
                continue
    except ImportError:
        pass
    except Exception as exc:
        print(f"ℹ google.genai SDK notice: {exc}", file=sys.stderr)

    # ── Method 2: Direct HTTP REST (v1 and v1beta with auto-retry) ───────────
    import time
    endpoints_to_try = [
        ("v1", "gemini-3.8-flash"),
        ("v1beta", "gemini-3.8-flash"),
        ("v1", "gemini-3.5-flash"),
        ("v1beta", "gemini-3.5-flash"),
    ]

    system_instruction = (
        "You are an expert DevOps engineer and senior code reviewer. "
        "Review the CI/CD scanner errors provided. For each error or group of related errors:\n"
        "1. State the file and line number (if available).\n"
        "2. Explain in 1-2 clear sentences what is wrong and why it matters.\n"
        "3. Provide the EXACT code fix using markdown code blocks (show Before / After where helpful).\n"
        "Be concise, practical, and prioritize security issues first."
    )

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
        },
    }).encode("utf-8")

    last_error = None
    for api_ver, m_name in endpoints_to_try:
        url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{m_name}:generateContent?key={clean_key}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    print(f"✅ Successfully generated fixes using {m_name} ({api_ver})")
                    return text, None
            except urllib.error.HTTPError as exc:
                err_msg = exc.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {exc.code} with model '{m_name}' ({api_ver}): {err_msg}"
                if exc.code == 503 and attempt == 0:
                    print(f"⏳ Google returned 503 (high demand) for {m_name}. Retrying in 2 seconds...", file=sys.stderr)
                    time.sleep(2)
                    continue
                if exc.code in (400, 403) and "API_KEY_INVALID" in err_msg:
                    return None, f"Invalid API Key: {err_msg}"
                break
            except Exception as exc:
                last_error = f"Connection error: {exc}"
                break

    return None, last_error






# ---------------------------------------------------------------------------
# File reader and error detection
# ---------------------------------------------------------------------------

def read_file_safe(path: str | None) -> str:
    """Safely read text file, returns empty string if missing or unreadable."""
    if not path:
        return ""
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return ""
    return p.read_text(encoding="utf-8", errors="replace").strip()


def detect_issues(tool_name: str, output: str) -> tuple[bool, int, list[str]]:
    """
    Analyzes scanner text output and returns:
    (has_issues, count_of_issues, sample_lines)
    """
    if not output or not output.strip():
        return False, 0, []

    lines = [line.strip() for line in output.splitlines() if line.strip()]

    # Filter out common success messages
    filtered = []
    for line in lines:
        lower = line.lower()
        if "all checks passed" in lower:
            continue
        if "no issues identified" in lower:
            continue
        if "0 errors" in lower and "0 warnings" in lower:
            continue
        filtered.append(line)

    if not filtered:
        return False, 0, []

    count = 0
    tool = tool_name.lower()

    if "ruff" in tool:
        # Matches typical ruff outputs: "path/file.py:line:col: RULE message"
        count = sum(1 for line in filtered if (": " in line and ":" in line.split()[0]))
    elif "bandit" in tool:
        # Bandit reports severity per issue: ">> Issue: [...]" or "Severity: High"
        count = sum(1 for line in filtered if line.startswith(">> Issue:") or "Severity:" in line)
    elif "eslint" in tool:
        # ESLint compact format: "file: line x, col y, Error/Warning - ..."
        count = sum(1 for line in filtered if "error" in line.lower() or "warning" in line.lower())
    elif "pytest" in tool:
        count = sum(1 for line in filtered if line.startswith("FAILED ") or " ERROR " in line)

    count = max(count, 1 if filtered else 0)
    return True, count, filtered[:10]


# ---------------------------------------------------------------------------
# HTML Report Builder (Interactive Web UI)
# ---------------------------------------------------------------------------

def build_html_report(
    active_scanners: list[tuple[str, str, str]],
    ai_suggestions: str | None,
    api_key_provided: bool,
    api_error_detail: str | None = None,
) -> str:

    """Builds a responsive, interactive standalone Web UI for code scan results."""
    import datetime

    total_issues = 0
    scanner_stats = {}
    for name, raw_text, icon in active_scanners:
        has_err, count, _ = detect_issues(name, raw_text)
        scanner_stats[name] = {"has_err": has_err, "count": count, "raw": raw_text, "icon": icon}
        if has_err:
            total_issues += count

    bandit_count = scanner_stats.get("Bandit (Security Scanner)", {}).get("count", 0)
    ruff_count = scanner_stats.get("Ruff (Python Linter)", {}).get("count", 0)
    eslint_count = scanner_stats.get("ESLint (JavaScript Linter)", {}).get("count", 0)
    pytest_count = scanner_stats.get("Pytest (Unit Tests)", {}).get("count", 0)



    is_passing = total_issues == 0
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Format AI suggestions into HTML (basic markdown to html translation)
    import html
    ai_html = ""
    if ai_suggestions:
        # Convert code blocks ```lang ... ``` into pre tags with copy buttons
        in_code_block = False
        code_lines = []
        code_block_id = 0
        for line in ai_suggestions.splitlines():
            if line.startswith("```"):
                if not in_code_block:
                    in_code_block = True
                    code_lines = []
                    lang = line.strip("`").strip() or "text"
                else:
                    in_code_block = False
                    code_block_id += 1
                    raw_code = "\n".join(code_lines)
                    escaped_code = html.escape(raw_code)
                    ai_html += f"""
                    <div class="code-wrapper">
                        <div class="code-header">
                            <span>{html.escape(lang.upper())}</span>
                            <button class="copy-btn" onclick="copyCode('code-{code_block_id}', this)">📋 Copy</button>
                        </div>
                        <pre id="code-{code_block_id}"><code>{escaped_code}</code></pre>
                    </div>
                    """
            elif in_code_block:
                code_lines.append(line)
            else:
                if line.startswith("### "):
                    ai_html += f"<h3 class='ai-h3'>{html.escape(line[4:])}</h3>"
                elif line.startswith("## "):
                    ai_html += f"<h2 class='ai-h2'>{html.escape(line[3:])}</h2>"
                elif line.startswith("# "):
                    ai_html += f"<h1 class='ai-h1'>{html.escape(line[2:])}</h1>"
                elif line.startswith("- ") or line.startswith("* "):
                    ai_html += f"<li class='ai-li'>{html.escape(line[2:])}</li>"
                elif line.strip():
                    ai_html += f"<p class='ai-p'>{html.escape(line)}</p>"
    elif not api_key_provided:
        ai_html = """
        <div class="alert-box alert-warning">
            <h4>⚠️ Gemini API Key Not Configured</h4>
            <p>To enable automated AI code fixes with before/after snippets:</p>
            <ul>
                <li><strong>On GitHub:</strong> Add <code>GEMINI_API_KEY</code> under <em>Repository Settings → Secrets and variables → Actions</em>.</li>
                <li><strong>Locally:</strong> Set <code>GEMINI_API_KEY=your_key</code> in your terminal or pass <code>--key YOUR_KEY</code>.</li>
            </ul>
        </div>
        """
    else:
        err_msg = html.escape(api_error_detail) if api_error_detail else "Unknown API error"
        ai_html = f"""
        <div class="alert-box alert-danger" style="background: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger); color: #FCA5A5; padding: 16px; border-radius: 8px;">
            <h4 style="margin-bottom: 8px;">⚠️ Gemini API Call Did Not Return Fixes</h4>
            <p style="margin-bottom: 8px;"><strong>Error details from Google Gemini:</strong></p>
            <pre style="background: rgba(0,0,0,0.4); padding: 10px; border-radius: 6px; font-size: 0.8rem; white-space: pre-wrap; word-break: break-all;"><code>{err_msg}</code></pre>
            <p style="margin-top: 10px; font-size: 0.85rem; color: #CBD5E1;">
                💡 <em>Tip: Verify that your API key is active and generated from <a href="https://aistudio.google.com/apikey" target="_blank" style="color: #38BDF8;">Google AI Studio</a>.</em>
            </p>
        </div>
        """


    # Build Raw Logs Sections
    raw_logs_html = ""
    for name, stat in scanner_stats.items():
        escaped_raw = html.escape(stat["raw"].strip()) if stat["raw"].strip() else "No logs recorded for this tool."
        badge = f"<span class='badge badge-danger'>{stat['count']} issues</span>" if stat["has_err"] else "<span class='badge badge-success'>Passed</span>"
        raw_logs_html += f"""
        <div class="card log-card">
            <div class="card-header flex-between" onclick="toggleDetails('{name.replace(' ', '_')}')">
                <div class="flex-align">
                    <span class="tool-icon">{stat['icon']}</span>
                    <strong>{html.escape(name)}</strong>
                </div>
                <div>{badge}</div>
            </div>
            <div id="{name.replace(' ', '_')}" class="card-body log-body">
                <pre><code>{escaped_raw}</code></pre>
            </div>
        </div>
        """

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CI/CD Code Scan & AI Fix Report</title>
    <style>
        :root {{
            --bg: #0F172A;
            --surface: #1E293B;
            --surface-hover: #334155;
            --border: #334155;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --primary: #38BDF8;
            --success: #10B981;
            --danger: #EF4444;
            --warning: #F59E0B;
            --code-bg: #090D16;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            line-height: 1.5;
            padding: 24px;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .logo-title {{ display: flex; align-items: center; gap: 12px; }}
        .logo-icon {{
            background: linear-gradient(135deg, #38BDF8, #6366F1);
            width: 44px; height: 44px; border-radius: 10px;
            display: flex; align-items: center; justify-content: center; font-size: 22px;
        }}
        h1 {{ font-size: 1.5rem; font-weight: 700; color: #fff; }}
        .subtitle {{ font-size: 0.85rem; color: var(--text-muted); }}
        .header-meta {{ display: flex; gap: 10px; align-items: center; }}
        .badge {{
            padding: 5px 12px; border-radius: 9999px; font-size: 0.8rem;
            font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
        }}
        .badge-success {{ background: rgba(16, 185, 129, 0.2); color: var(--success); border: 1px solid var(--success); }}
        .badge-danger {{ background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); }}
        .badge-warning {{ background: rgba(245, 158, 11, 0.2); color: var(--warning); border: 1px solid var(--warning); }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px; margin-bottom: 28px;
        }}
        .kpi-card {{
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 10px; padding: 18px 20px;
        }}
        .kpi-val {{ font-size: 2.2rem; font-weight: 800; line-height: 1.1; margin-bottom: 4px; }}
        .kpi-val.danger {{ color: var(--danger); }}
        .kpi-val.success {{ color: var(--success); }}
        .kpi-label {{ font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}

        .tabs {{ display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 12px; overflow-x: auto; }}
        .tab-btn {{
            background: transparent; border: 1px solid transparent; color: var(--text-muted);
            padding: 8px 16px; border-radius: 6px; font-weight: 600; font-size: 0.9rem; cursor: pointer;
            transition: all 0.2s; white-space: nowrap;
        }}
        .tab-btn:hover {{ color: #fff; background: var(--surface-hover); }}
        .tab-btn.active {{ background: #38BDF8; color: #0F172A; }}

        .card {{
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 10px; margin-bottom: 20px; overflow: hidden;
        }}
        .card-header {{ padding: 14px 20px; border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.02); }}
        .card-body {{ padding: 20px; }}
        .flex-between {{ display: flex; justify-content: space-between; align-items: center; }}
        .flex-align {{ display: flex; align-items: center; gap: 8px; }}
        .tool-icon {{ font-size: 1.2rem; }}

        /* AI Fix Content Styling */
        .ai-h1 {{ font-size: 1.4rem; color: #38BDF8; margin: 16px 0 10px; }}
        .ai-h2 {{ font-size: 1.2rem; color: #F8FAFC; margin: 16px 0 8px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }}
        .ai-h3 {{ font-size: 1.05rem; color: #F59E0B; margin: 14px 0 6px; }}
        .ai-p {{ margin-bottom: 10px; color: #CBD5E1; font-size: 0.95rem; }}
        .ai-li {{ margin-left: 20px; margin-bottom: 6px; color: #CBD5E1; }}

        /* Code Blocks */
        .code-wrapper {{
            background: var(--code-bg); border: 1px solid var(--border);
            border-radius: 8px; margin: 12px 0 16px; overflow: hidden;
        }}
        .code-header {{
            display: flex; justify-content: space-between; align-items: center;
            background: #151D2C; padding: 6px 14px; font-size: 0.75rem; color: var(--text-muted);
            border-bottom: 1px solid rgba(255,255,255,0.05); font-family: monospace;
        }}
        .copy-btn {{
            background: var(--surface); border: 1px solid var(--border); color: #CBD5E1;
            padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; cursor: pointer;
        }}
        .copy-btn:hover {{ background: #38BDF8; color: #000; }}
        pre {{
            padding: 14px; overflow-x: auto; font-family: "JetBrains Mono", Consolas, Menlo, monospace;
            font-size: 0.88rem; line-height: 1.45; color: #E2E8F0;
        }}
        .alert-box {{
            padding: 16px 20px; border-radius: 8px; margin-bottom: 16px;
        }}
        .alert-warning {{ background: rgba(245, 158, 11, 0.1); border: 1px solid var(--warning); color: #FDE68A; }}
        .alert-warning ul {{ margin-left: 20px; margin-top: 8px; }}

        /* Collapsible Logs */
        .log-card .card-header {{ cursor: pointer; }}
        .log-body {{ display: block; }}
        .log-body.collapsed {{ display: none; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo-title">
                <div class="logo-icon">🛡️</div>
                <div>
                    <h1>CI/CD Code Scanner & AI Fix Report</h1>
                    <div class="subtitle">Multi-Scanner Security & Quality Dashboard · Generated at {now_str}</div>
                </div>
            </div>
            <div class="header-meta">
                <span class="badge { 'badge-success' if is_passing else 'badge-danger' }">
                    { 'PASSING · All Clean' if is_passing else f'FAILING · {total_issues} Issues Found' }
                </span>
            </div>
        </header>

        <!-- KPI Summary Cards -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-val { 'danger' if total_issues > 0 else 'success' }">{total_issues}</div>
                <div class="kpi-label">Total Code Issues</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-val { 'danger' if bandit_count > 0 else 'success' }">{bandit_count}</div>
                <div class="kpi-label">Security Flaws (Bandit)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-val { 'danger' if ruff_count > 0 else 'success' }">{ruff_count}</div>
                <div class="kpi-label">Python Lints (Ruff)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-val { 'danger' if eslint_count > 0 else 'success' }">{eslint_count}</div>
                <div class="kpi-label">JavaScript Bugs (ESLint)</div>
            </div>
        </div>


        <!-- Navigation Tabs -->
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('ai-fixes', this)">🤖 AI Fix Suggestions</button>
            <button class="tab-btn" onclick="switchTab('raw-logs', this)">📋 Raw Scanner Logs</button>
        </div>

        <!-- Tab 1: AI Fix Suggestions -->
        <div id="tab-ai-fixes" class="tab-content">
            <div class="card">
                <div class="card-header flex-between">
                    <strong>🤖 Google Gemini AI — Targeted Code Fixes</strong>
                    <span class="badge badge-warning">Auto-Generated Remediation</span>
                </div>
                <div class="card-body">
                    {ai_html}
                </div>
            </div>
        </div>

        <!-- Tab 2: Raw Scanner Logs -->
        <div id="tab-raw-logs" class="tab-content" style="display: none;">
            {raw_logs_html}
        </div>
    </div>

    <script>
        function switchTab(tabId, btn) {{
            document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById('tab-' + tabId).style.display = 'block';
            btn.classList.add('active');
        }}

        function toggleDetails(id) {{
            const el = document.getElementById(id);
            if (el) {{
                el.classList.toggle('collapsed');
            }}
        }}

        function copyCode(preId, btn) {{
            const codeEl = document.getElementById(preId);
            if (!codeEl) return;
            navigator.clipboard.writeText(codeEl.innerText).then(() => {{
                const originalText = btn.innerText;
                btn.innerText = '✅ Copied!';
                btn.style.background = '#10B981';
                btn.style.color = '#fff';
                setTimeout(() => {{
                    btn.innerText = originalText;
                    btn.style.background = '';
                    btn.style.color = '';
                }}, 2000);
            }});
        }}
    </script>
</body>
</html>"""
    return html_template


def build_markdown_report(
    active_scanners: list[tuple[str, str, str]],  # (name, raw_output, icon)
    ai_suggestions: str | None,
    api_key_provided: bool,
) -> str:
    """Assembles a clean, developer-friendly Markdown report."""
    sections: list[str] = []

    sections.append("# 🔍 Automated Code Scan & AI Fix Report")
    sections.append("> Triggered by CI/CD Pipeline · Analyzed by Multi-Scanner Suite\n")

    # 1. Summary Table
    sections.append("## 📊 Scan Summary\n")
    sections.append("| Tool | Scope | Status | Issues |")
    sections.append("|---|---|---|---|")

    total_issues = 0
    has_any_errors = False

    for name, raw_text, icon in active_scanners:
        has_err, count, _ = detect_issues(name, raw_text)
        if has_err:
            has_any_errors = True
            total_issues += count
            status_badge = f"❌ **Failing**"
            count_str = f"`{count} issue{'s' if count != 1 else ''}`"
        else:
            status_badge = "✅ **Passed**"
            count_str = "`0`"

        sections.append(f"| {icon} {name} | Automated check | {status_badge} | {count_str} |")

    sections.append("")

    if not has_any_errors:
        sections.append("### 🎉 All Scans Passed Cleanly!")
        sections.append("No security vulnerabilities, linting errors, or test failures were detected.")
        return "\n".join(sections)

    sections.append(f"**Found a total of {total_issues} issue(s) requiring attention.**\n")
    sections.append("---\n")

    # 2. Detailed Tool Outputs
    sections.append("## 📋 Scanner Output Details\n")
    for name, raw_text, icon in active_scanners:
        has_err, count, _ = detect_issues(name, raw_text)
        if has_err:
            sections.append(f"### {icon} {name} ({count} issues)")
            sections.append("<details open><summary>Click to view raw scanner logs</summary>\n")
            sections.append("```text")
            sections.append(raw_text.strip()[:4000])  # limit per tool to prevent exceeding GitHub comment size
            sections.append("```\n")
            sections.append("</details>\n")

    # 3. AI-Powered Fix Recommendations
    sections.append("---\n")
    sections.append("## 🤖 AI-Generated Fix Recommendations (Google Gemini)\n")

    if ai_suggestions:
        sections.append(ai_suggestions)
    elif not api_key_provided:
        sections.append(
            "> ⚠️ **Gemini API Key was not detected.**\n"
            ">\n"
            "> To enable automatic code fix suggestions with before/after snippets:\n"
            "> 1. Add `GEMINI_API_KEY` to your GitHub Repository Secrets (`Settings` → `Secrets and variables` → `Actions`).\n"
            "> 2. For local testing, run `set GEMINI_API_KEY=your_key` or place it in your `.env` file."
        )
    else:
        sections.append(
            "> ⚠️ AI analysis could not be completed for this run. Review the raw logs above to resolve the issues."
        )

    sections.append("\n---\n*Report generated automatically. Push code updates to re-trigger this scan.*")
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# AI Prompt formulation
# ---------------------------------------------------------------------------

def construct_ai_prompt(active_scanners: list[tuple[str, str, str]]) -> str:
    """Builds a rich, targeted prompt containing only the actual failing logs."""
    failing_sections = []

    for name, raw_text, _ in active_scanners:
        has_err, _, _ = detect_issues(name, raw_text)
        if has_err:
            failing_sections.append(f"### Tool: {name}\n```\n{raw_text[:3500]}\n```")

    if not failing_sections:
        return ""

    joined_errors = "\n\n".join(failing_sections)

    prompt = textwrap.dedent(f"""
        Please review the following code scan findings from our automated CI/CD pipeline.
        These are from a Python (FastAPI) and/or JavaScript (React) project.

        For every issue identified in the scanner output:
        1. Identify the file name, line number, and error code.
        2. Give a brief, plain-English explanation of why this is a problem.
        3. Provide the EXACT code fix (showing Before vs After code where appropriate).

        SCANNER FINDINGS:
        {joined_errors}
    """)
    return prompt.strip()


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-scanner report aggregator with AI fix suggestions")
    parser.add_argument("--ruff", help="Path to Ruff output text file")
    parser.add_argument("--bandit", help="Path to Bandit output text file")
    parser.add_argument("--eslint", help="Path to ESLint output text file")
    parser.add_argument("--pytest", help="Path to Pytest output text file")
    parser.add_argument("--output", required=True, help="Path where the final markdown report should be saved")
    parser.add_argument("--html", help="Path where the interactive HTML web UI should be saved")
    parser.add_argument("--gemini-key", help="Optional explicit Gemini API key", default="")

    args = parser.parse_args()

    # Collect only the tools that were actually configured / passed
    active_scanners: list[tuple[str, str, str]] = []

    if args.ruff:
        active_scanners.append(("Ruff (Python Linter)", read_file_safe(args.ruff), "🐍"))
    if args.bandit:
        active_scanners.append(("Bandit (Security Scanner)", read_file_safe(args.bandit), "🔒"))
    if args.eslint:
        active_scanners.append(("ESLint (JavaScript Linter)", read_file_safe(args.eslint), "⚛️"))
    if args.pytest:
        active_scanners.append(("Pytest (Unit Tests)", read_file_safe(args.pytest), "🧪"))

    api_key = resolve_gemini_api_key(args.gemini_key)
    ai_suggestions: str | None = None
    ai_error_detail: str | None = None

    # Check if there are any errors to send to AI
    prompt = construct_ai_prompt(active_scanners)

    if prompt and api_key:
        print("🤖 Contacting Gemini AI for code fix suggestions...")
        ai_suggestions, ai_error_detail = call_gemini(prompt, api_key)
        if ai_suggestions:
            print("✅ Gemini successfully provided fix suggestions.")
        else:
            print(f"⚠ Gemini request failed: {ai_error_detail}")
    elif prompt and not api_key:
        print("ℹ Scans found issues, but no GEMINI_API_KEY was found. Skipping AI suggestions.")
    else:
        print("✅ No scan errors detected across active tools.")

    # Assemble report
    report_md = build_markdown_report(
        active_scanners=active_scanners,
        ai_suggestions=ai_suggestions,
        api_key_provided=bool(api_key),
    )

    out_file = Path(args.output)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report_md, encoding="utf-8")
    print(f"📄 Markdown Report generated at: {out_file.resolve()}")

    # Assemble and write HTML report if requested
    if args.html:
        report_html = build_html_report(
            active_scanners=active_scanners,
            ai_suggestions=ai_suggestions,
            api_key_provided=bool(api_key),
            api_error_detail=ai_error_detail,
        )
        html_file = Path(args.html)
        html_file.parent.mkdir(parents=True, exist_ok=True)
        html_file.write_text(report_html, encoding="utf-8")
        print(f"🌐 Web UI Report generated at: {html_file.resolve()}")



    # Determine if any scanner had errors
    has_errors = any(detect_issues(name, raw)[0] for name, raw, _ in active_scanners)
    if has_errors:
        print("❌ One or more scanners detected code issues.")
    else:
        print("🎉 All checks passed cleanly.")


if __name__ == "__main__":
    main()
