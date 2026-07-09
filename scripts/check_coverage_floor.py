#!/usr/bin/env python
"""Per-module coverage floor gate.

The aggregate ``--cov-fail-under`` gate can hide a weak module behind a
healthy average (explore.py once sat at 47% while the project total showed
82%). This script reads a coverage.py JSON report and fails if ANY measured
module falls below the floor, so a single neglected file reddens CI on its
own.

Usage:
    pytest tests/ --cov=trendspyg --cov-report=json -m "not network"
    python scripts/check_coverage_floor.py [--floor 75] [--report coverage.json]

Exit codes:
    0 - every module is at or above the floor
    1 - at least one module is below the floor
    2 - report missing, unreadable, or empty
"""

import argparse
import json
import sys

DEFAULT_FLOOR = 75.0
DEFAULT_REPORT = "coverage.json"


def load_report(path):
    """Load the coverage JSON report, or exit 2 with an actionable message."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(
            f"ERROR: {path} not found. Generate it first:\n"
            '  pytest tests/ --cov=trendspyg --cov-report=json -m "not network"',
            file=sys.stderr,
        )
        sys.exit(2)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: could not read {path}: {exc}", file=sys.stderr)
        sys.exit(2)


def find_offenders(files, floor):
    """Return [(module, percent)] for every measured file below the floor."""
    offenders = []
    for raw_path in sorted(files):
        percent = files[raw_path]["summary"]["percent_covered"]
        if percent < floor:
            offenders.append((raw_path.replace("\\", "/"), percent))
    return offenders


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--floor",
        type=float,
        default=DEFAULT_FLOOR,
        help=f"minimum per-module coverage percent (default: {DEFAULT_FLOOR:g})",
    )
    parser.add_argument(
        "--report",
        default=DEFAULT_REPORT,
        help=f"path to the coverage JSON report (default: {DEFAULT_REPORT})",
    )
    args = parser.parse_args(argv)

    report = load_report(args.report)
    files = report.get("files") or {}
    if not files:
        print(
            f"ERROR: no per-file coverage data in {args.report} - " "was pytest run with --cov?",
            file=sys.stderr,
        )
        return 2

    try:
        offenders = find_offenders(files, args.floor)
        lowest_path, lowest_pct = min(
            ((p.replace("\\", "/"), d["summary"]["percent_covered"]) for p, d in files.items()),
            key=lambda item: item[1],
        )
    except (KeyError, TypeError) as exc:
        print(f"ERROR: unexpected report structure in {args.report}: {exc}", file=sys.stderr)
        return 2

    if offenders:
        print(f"FAIL: {len(offenders)} module(s) below the {args.floor:g}% coverage floor:")
        for module, percent in offenders:
            print(f"  {module}: {percent:.1f}%")
        return 1

    print(
        f"OK: all {len(files)} modules >= {args.floor:g}% "
        f"(lowest: {lowest_path} at {lowest_pct:.1f}%)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
