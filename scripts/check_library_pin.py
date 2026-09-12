#!/usr/bin/env python3
"""Assert that manifest.json's pinned aiosecurityspy version is on PyPI.

This repository always consumes the published `aiosecurityspy` package
(AD-14): there is no in-tree copy of the library, and nothing here resolves
one. `manifest.json`'s pin is what Home Assistant pip-installs at setup, so a
release cannot ship a pin that cannot resolve there.

To test against an unreleased library change: publish it as a PyPI
pre-release from the standalone `aljopro/aiosecurityspy` repo (e.g.
`0.2.1a1` -- pip/uv never resolve a pre-release unless pinned exactly), then
point this repository's `manifest.json` and `pyproject.toml` dev dependency
at that exact version temporarily. Revert both once the real release ships.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "custom_components" / "securityspy" / "manifest.json"
PACKAGE = "aiosecurityspy"
HTTP_OK = 200
HTTP_NOT_FOUND = 404


def pinned_version() -> str:
    """Return the version manifest.json pins, or exit with a clear message."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for requirement in manifest.get("requirements", []):
        match = re.fullmatch(rf"{PACKAGE}==(.+)", requirement.strip())
        if match:
            return match.group(1)
    found = manifest.get("requirements")
    sys.exit(f"manifest.json does not pin {PACKAGE} with '=='; found: {found}")


def is_on_pypi(version: str) -> bool:
    """Return whether this exact version is published."""
    url = f"https://pypi.org/pypi/{PACKAGE}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return bool(response.status == HTTP_OK)
    except urllib.error.HTTPError as err:
        if err.code == HTTP_NOT_FOUND:
            return False
        raise


def main() -> int:
    """Assert the pinned version exists on PyPI."""
    pinned = pinned_version()
    if is_on_pypi(pinned):
        print(f"ok: {PACKAGE} {pinned} is published")
        return 0
    print(f"FAIL: manifest.json pins {PACKAGE}=={pinned}, which is not on PyPI.")
    print("      Home Assistant pip-installs this at setup, so a HACS install would fail.")
    print("      Publish the library before releasing the integration.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
