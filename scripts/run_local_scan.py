#!/usr/bin/env python3
"""
run_local_scan.py — Test the entire scan & AI fix pipeline on your local machine!

This allows you to see the EXACT report and Gemini AI fix suggestions
BEFORE pushing any code to GitHub.

How to run:
    python scripts/run_local_scan.py

Optional:
    python scripts/run_local_scan.py --simulate
    (Injects a sample security & lint error to verify the AI prompt and report formatting)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path


def run_command(cmd: list[str], output_file: Path) -> int:
    """Runs a shell tool and captures output to file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        output_file.write_text(combined.strip(), encoding="utf-8")
        return res.returncode
    except FileNotFoundError:
        output_file.write_text(f"Tool not installed: {cmd[0]}", encoding="utf-8")
        return -1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CI/CD scanning locally")
    parser.add_argument("--simulate", action="store_true", help="Simulate sample errors to test AI fixes without installing all linters")
    parser.add_argument("--key", help="Gemini API Key (optional if set in env or .env)", default="")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch the Web UI in the default browser")
    args = parser.parse_args()


    repo_root = Path(__file__).parent.parent.resolve()
    os.chdir(repo_root)

    results_dir = repo_root / "scan-results"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print(" 🚀 LOCAL CODE SCANNER & AI FIX GENERATOR")
    print("=" * 65)

    ruff_out = results_dir / "ruff.txt"
    bandit_out = results_dir / "bandit.txt"
    pytest_out = results_dir / "pytest.txt"
    eslint_out = results_dir / "eslint.txt"

    if args.simulate:
        print("\n🧪 [Simulation Mode Active]")
        print("Injecting realistic sample findings for Ruff, Bandit, and ESLint...")

        ruff_out.write_text(
            "audit-tool/app/engine.py:12:1: F401 `os` imported but unused\n"
            "audit-tool/app/engine.py:45:10: UP032 [*] Use f-string instead of `format` call\n"
            "audit-tool/app/routes/audits.py:7:1: I001 [*] Import block is un-sorted or un-formatted",
            encoding="utf-8"
        )

        bandit_out.write_text(
            ">> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'secret123'\n"
            "   Severity: Medium   Confidence: Medium\n"
            "   Location: audit-tool/app/config.py:28:15\n"
            "28     DEFAULT_DEV_TOKEN = 'secret123'\n\n"
            ">> Issue: [B608:hardcoded_sql_expressions] Possible SQL injection vector through string format\n"
            "   Severity: High   Confidence: Medium\n"
            "   Location: audit-tool/app/engine.py:100:18\n"
            "100    query = f\"SELECT * FROM users WHERE dept = '{user_input}'\"",
            encoding="utf-8"
        )

        eslint_out.write_text(
            "audit-dashboard/src/App.jsx: line 24, col 9, Error - 'unusedState' is defined but never used. (no-unused-vars)\n"
            "audit-dashboard/src/App.jsx: line 150, col 5, Warning - Missing 'key' prop for element in iterator (react/jsx-key)",
            encoding="utf-8"
        )

        pytest_out.write_text(
            "tests/test_engine.py::test_rule_loader PASSED\n"
            "tests/test_engine.py::test_sql_builder FAILED\n\n"
            "    def test_sql_builder():\n"
            ">       assert build_sql_query({'id': 'unknown'}) != ''\n"
            "E       AssertionError: assert '' != ''",
            encoding="utf-8"
        )
    else:
        print("\n🔍 Scanning local codebase...")

        # 1. Ruff
        if shutil.which("ruff"):
            print("  ▶ Running Ruff on audit-tool/...")
            run_command(["ruff", "check", "audit-tool/"], ruff_out)
        else:
            print("  ℹ Ruff not installed locally. Run 'pip install ruff' or use '--simulate'")
            ruff_out.write_text("", encoding="utf-8")

        # 2. Bandit
        if shutil.which("bandit"):
            print("  ▶ Running Bandit on audit-tool/...")
            run_command(["bandit", "-r", "audit-tool/", "-f", "txt", "--severity-level", "medium"], bandit_out)
        else:
            print("  ℹ Bandit not installed locally. Run 'pip install bandit' or use '--simulate'")
            bandit_out.write_text("", encoding="utf-8")

        # 3. Pytest
        if shutil.which("pytest"):
            print("  ▶ Running Pytest...")
            run_command([sys.executable, "-m", "pytest", "audit-tool/tests", "-q", "--tb=short"], pytest_out)
        else:
            pytest_out.write_text("", encoding="utf-8")

        # 4. ESLint
        npx_bin = shutil.which("npx") or shutil.which("npx.cmd")
        if npx_bin and Path("audit-dashboard").exists():
            print("  ▶ Running ESLint on audit-dashboard/...")
            run_command([npx_bin, "eslint", "src/", "--format", "compact"], eslint_out)
        else:
            eslint_out.write_text("", encoding="utf-8")

    # Now run AI fix script
    report_output = results_dir / "local-ai-report.md"
    html_output = results_dir / "report.html"
    print("\n🤖 Running AI Fix Suggestions Generator...")

    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "ai_fix_suggestions.py"),
        "--ruff", str(ruff_out),
        "--bandit", str(bandit_out),
        "--eslint", str(eslint_out),
        "--pytest", str(pytest_out),
        "--output", str(report_output),
        "--html", str(html_output),
    ]

    if args.key:
        cmd.extend(["--gemini-key", args.key])

    proc = subprocess.run(cmd)

    if proc.returncode == 0:
        html_uri = html_output.as_uri()
        print("\n" + "=" * 65)
        print(" 🎉 SCAN COMPLETE!")
        print(f" 🌐 Interactive Web UI: {html_uri}")
        print(f" 📄 Markdown Report:    {report_output.resolve()}")
        print("=" * 65)

        if not args.no_browser:
            import webbrowser
            print("🚀 Launching interactive Web UI in your browser...")
            webbrowser.open(html_uri)
    else:
        print("\n❌ Scanner script exited with an error.")



if __name__ == "__main__":
    main()
