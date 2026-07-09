"""Tests for scripts/check_coverage_floor.py (the per-module coverage gate).

The gate guards CI, so the gate itself gets tested: a checker that silently
passes everything (or crashes on a missing report) is worse than no checker.
Runs the script as a subprocess, exactly as CI invokes it.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_coverage_floor.py"


def make_report(percents):
    """Build a minimal coverage.py JSON report from {module: percent}."""
    return {
        "files": {name: {"summary": {"percent_covered": pct}} for name, pct in percents.items()}
    }


def run_gate(tmp_path, report=None, args=()):
    """Write `report` as coverage.json in tmp_path and run the gate there."""
    if report is not None:
        (tmp_path / "coverage.json").write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )


class TestCoverageFloorGate:
    def test_all_modules_above_floor_passes(self, tmp_path):
        report = make_report({"trendspyg/a.py": 95.0, "trendspyg/b.py": 82.5})
        result = run_gate(tmp_path, report)
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_module_below_floor_fails_and_is_named(self, tmp_path):
        # The historical failure mode: one weak module hidden by a healthy average.
        report = make_report({"trendspyg/rss.py": 95.0, "trendspyg/explore.py": 47.0})
        result = run_gate(tmp_path, report)
        assert result.returncode == 1
        assert "explore.py" in result.stdout
        assert "47.0%" in result.stdout

    def test_exact_floor_boundary_passes(self, tmp_path):
        report = make_report({"trendspyg/a.py": 80.0})
        result = run_gate(tmp_path, report, args=["--floor", "80"])
        assert result.returncode == 0

    def test_default_floor_is_80(self, tmp_path):
        # Pins the gate policy: raising or lowering DEFAULT_FLOOR must be deliberate.
        result = run_gate(tmp_path, make_report({"trendspyg/a.py": 79.9}))
        assert result.returncode == 1
        result = run_gate(tmp_path, make_report({"trendspyg/a.py": 80.0}))
        assert result.returncode == 0

    def test_floor_flag_overrides_default(self, tmp_path):
        report = make_report({"trendspyg/a.py": 90.0})
        result = run_gate(tmp_path, report, args=["--floor", "95"])
        assert result.returncode == 1
        assert "a.py" in result.stdout

    def test_windows_path_keys_normalized_in_output(self, tmp_path):
        report = make_report({"trendspyg\\cli.py": 10.0})
        result = run_gate(tmp_path, report)
        assert result.returncode == 1
        assert "trendspyg/cli.py" in result.stdout

    def test_missing_report_exits_2_with_hint(self, tmp_path):
        result = run_gate(tmp_path, report=None)
        assert result.returncode == 2
        assert "not found" in result.stderr
        assert "--cov-report=json" in result.stderr

    def test_malformed_json_exits_2(self, tmp_path):
        (tmp_path / "coverage.json").write_text("{not json", encoding="utf-8")
        result = run_gate(tmp_path)
        assert result.returncode == 2
        assert "ERROR" in result.stderr

    def test_empty_files_section_exits_2(self, tmp_path):
        result = run_gate(tmp_path, {"files": {}, "totals": {}})
        assert result.returncode == 2
        assert "no per-file coverage data" in result.stderr

    def test_unexpected_structure_exits_2(self, tmp_path):
        result = run_gate(tmp_path, {"files": {"trendspyg/a.py": {"summary": {}}}})
        assert result.returncode == 2
        assert "unexpected report structure" in result.stderr
