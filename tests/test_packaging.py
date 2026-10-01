"""Every trendspyg subpackage must be listed for the wheel.

Incident (2026-10-02, 1.9.0): the new ``trendspyg.compat`` package was missing
from ``[tool.setuptools] packages`` while all tests passed, because the tests
import from the source tree. The built wheel shipped without it; only a check
of the wheel's contents caught it. This test makes that mistake fail here.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _listed_packages():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^\[tool\.setuptools\]\s*\npackages\s*=\s*\[(.*?)\]", text, re.M | re.S)
    assert match, "pyproject.toml must list packages under [tool.setuptools]"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def _packages_on_disk():
    package_root = ROOT / "trendspyg"
    return {
        ".".join(init.parent.relative_to(ROOT).parts)
        for init in package_root.rglob("__init__.py")
        if "__pycache__" not in init.parts
    }


def test_every_subpackage_ships_in_the_wheel():
    missing = _packages_on_disk() - _listed_packages()
    assert not missing, f"add to [tool.setuptools] packages in pyproject.toml: {sorted(missing)}"


def test_no_listed_package_is_missing_on_disk():
    stale = _listed_packages() - _packages_on_disk()
    assert not stale, f"listed in pyproject.toml but not on disk: {sorted(stale)}"
