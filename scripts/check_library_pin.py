#!/usr/bin/env python3
"""Assert that manifest.json's library pin matches the library it is built against.

This is the check whose absence let the standalone `aiosecurityspy` repository
drift 1,620 lines behind the in-tree copy without anything going red. The
integration's tests resolve the library through `[tool.uv.sources]` as a local
editable path, so they prove nothing about the version a HACS user actually
installs -- `manifest.json`'s pin is what Home Assistant pip-installs at setup.

Run in two modes:

* **dev** (default) -- compare the pin against the local library's
  `pyproject.toml` version. Catches "we bumped one and forgot the other".
* ``--released`` -- additionally assert the pinned version exists on PyPI, so a
  release cannot ship a pin that cannot resolve.

The library's location comes from ``AIOSECURITYSPY_PATH`` (default
``../aiosecurityspy``), because uv cannot interpolate environment variables into
``[tool.uv.sources]`` paths -- the path there must stay a literal relative path,
so every *other* consumer of that location reads it from the environment
instead.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "custom_components" / "securityspy" / "manifest.json"
DEFAULT_LIBRARY_PATH = "../aiosecurityspy"
PACKAGE = "aiosecurityspy"
HTTP_OK = 200
HTTP_NOT_FOUND = 404


def library_path() -> Path:
    """Return the library checkout location, from the environment or the default."""
    raw = os.environ.get("AIOSECURITYSPY_PATH", DEFAULT_LIBRARY_PATH)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    return candidate


def pinned_version() -> str:
    """Return the version manifest.json pins, or exit with a clear message."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for requirement in manifest.get("requirements", []):
        match = re.fullmatch(rf"{PACKAGE}==(.+)", requirement.strip())
        if match:
            return match.group(1)
    found = manifest.get("requirements")
    sys.exit(f"manifest.json does not pin {PACKAGE} with '=='; found: {found}")


def local_version(path: Path) -> str | None:
    """Return the library's own declared version, or None when it is not checked out."""
    pyproject = path / "pyproject.toml"
    if not pyproject.is_file():
        return None
    return str(tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"])


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
    """Compare the pin against the local library and, with --released, against PyPI."""
    pinned = pinned_version()
    path = library_path()
    local = local_version(path)

    if local is None:
        print(f"note: no library checkout at {path}; skipping the local-version comparison")
        print("      set AIOSECURITYSPY_PATH if it lives elsewhere")
    elif local != pinned:
        print(f"FAIL: manifest.json pins {PACKAGE}=={pinned}, but {path} declares {local}.")
        print("      Bump one to match the other; they are released together.")
        return 1
    else:
        print(f"ok: manifest pin and local library agree at {pinned}")

    if "--released" in sys.argv:
        if is_on_pypi(pinned):
            print(f"ok: {PACKAGE} {pinned} is published")
        else:
            print(f"FAIL: manifest.json pins {PACKAGE}=={pinned}, which is not on PyPI.")
            print("      Home Assistant pip-installs this at setup, so a HACS install would fail.")
            print("      Publish the library before releasing the integration.")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
