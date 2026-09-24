"""
scripts/verify_release.py

Pre-flight release gate for ki-manager:
1. Runs full test suite (including unit tests and MCP E2E tests).
2. Builds distribution artifacts (wheel and sdist).
3. Verifies CLI entrypoints.
"""

import sys
import subprocess
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_step(name: str, cmd: list, cwd: Path = REPO_ROOT):
    print(f"\n[STEP] {name}")
    print(f"Command: {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd, text=True)
    if result.returncode != 0:
        print(f"\n[FAIL] {name} exited with code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"[OK] {name}")


def main():
    print("=" * 60)
    print("  ki-manager Pre-flight Release Verification Gate")
    print("=" * 60)

    # 1. Run all tests
    run_step("Full Test Suite (pytest)", [sys.executable, "-m", "pytest", "tests/", "-v"])

    # 2. Build distributions
    run_step("Build Distributions (sdist & wheel)", [sys.executable, "-m", "build"])

    # 3. Verify CLI
    run_step("Verify CLI Help", [sys.executable, "-m", "ki_manager.cli", "--help"])
    run_step("Verify CLI Version", [sys.executable, "-m", "ki_manager.cli", "--version"])

    print("\n" + "=" * 60)
    print("  [SUCCESS] All verification checks passed! Project is ready for release.")
    print("=" * 60)


if __name__ == "__main__":
    main()
