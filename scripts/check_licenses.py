"""License compatibility check for the aereo distribution.

Fails CI if any installed dependency uses a license incompatible with
Apache-2.0 (the aereo top-level license).

Policy
------
Apache-2.0 is permissive but *cannot* be combined with copyleft licenses
that would force the entire combined work to be relicensed. In particular:

- GPL (any version) is incompatible — including via dynamic Python imports
  per the FSF position. Apache Software Foundation policy explicitly
  forbids GPL deps in Apache projects (Category X).
- AGPL is incompatible for the same reason, plus an extra network-clause.
- LGPL is *compatible* when used as an unmodified runtime dependency
  (which is always the case for ``pip install`` deps).
- MPL/EPL are compatible at file boundaries.
- BSD/MIT/Apache/ISC are trivially compatible.

Run locally
-----------
    uv pip install pip-licenses
    uv run python scripts/check_licenses.py

The check is intentionally run against the *runtime* dep set, not the dev
group. If you run it inside a full dev env you may see warnings for
dev-only tools (e.g. ``satpy``, used only in development) — those are
expected and are not blockers for distribution.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

DISALLOWED_PATTERNS = [
    re.compile(r"\bGPL[ -]?v?2\b", re.IGNORECASE),
    re.compile(r"\bGPL[ -]?v?3\b", re.IGNORECASE),
    re.compile(r"\bGPL-2\.0", re.IGNORECASE),
    re.compile(r"\bGPL-3\.0", re.IGNORECASE),
    re.compile(r"\bAGPL", re.IGNORECASE),
    re.compile(r"GNU General Public License", re.IGNORECASE),
    re.compile(r"GNU Affero", re.IGNORECASE),
]

ALLOWED_OVERRIDES = {
    re.compile(r"\bLGPL", re.IGNORECASE),
    re.compile(r"\bLesser General Public License", re.IGNORECASE),
}

KNOWN_FALSE_POSITIVES: dict[str, str] = {
    "docutils": (
        "Tri-licensed (BSD; GPL; Public Domain). Only the BSD/Public Domain "
        "portions are used by upstream consumers like Sphinx. Apache projects "
        "including Airflow, Celery and Beam treat docutils as permissive."
    ),
}


def fetch_licenses() -> list[dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json", "--with-urls"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        proc = subprocess.run(
            ["pip-licenses", "--format=json", "--with-urls"],
            capture_output=True,
            text=True,
            check=True,
        )
    return json.loads(proc.stdout)


def is_disallowed(license_str: str) -> bool:
    if any(rx.search(license_str) for rx in ALLOWED_OVERRIDES):
        return False
    return any(rx.search(license_str) for rx in DISALLOWED_PATTERNS)


def main() -> int:
    packages = fetch_licenses()
    violations: list[tuple[str, str, str]] = []
    for pkg in packages:
        name = pkg.get("Name", "?")
        version = pkg.get("Version", "?")
        license_str = pkg.get("License", "UNKNOWN") or "UNKNOWN"
        if name in KNOWN_FALSE_POSITIVES:
            continue
        if is_disallowed(license_str):
            violations.append((name, version, license_str))

    if violations:
        print("License-compat check FAILED.\n", file=sys.stderr)
        print(
            "The following dependencies use licenses incompatible with the "
            "aereo Apache-2.0 license:\n",
            file=sys.stderr,
        )
        for name, version, lic in violations:
            print(f"  - {name} {version}: {lic}", file=sys.stderr)
        print(
            "\nResolution:\n"
            "  1. Remove or replace the offending dependency, OR\n"
            "  2. If it is a false-positive (e.g. dual-licensed), add it to\n"
            "     KNOWN_FALSE_POSITIVES in scripts/check_licenses.py with a\n"
            "     justification comment.\n"
            "\nSee CONTRIBUTING.md for the license policy.\n",
            file=sys.stderr,
        )
        return 1

    print(f"License-compat check OK ({len(packages)} packages scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
