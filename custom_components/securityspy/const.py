"""Constants shared across the SecuritySpy integration.

Anything that is a *fact about SecuritySpy* belongs to ``aiosecurityspy`` and is
re-exported here rather than restated (AD-2). Only Home Assistant-side names --
the domain -- originate in this module.
"""

from __future__ import annotations

from typing import Final

from aiosecurityspy import DEFAULT_PORT as _LIBRARY_DEFAULT_PORT

#: Integration domain. Must match the directory name and ``manifest.json``.
DOMAIN: Final = "securityspy"

#: SecuritySpy's default web-server port, taken from the library so the config
#: flow's default cannot drift from what the client actually uses.
DEFAULT_PORT: Final[int] = _LIBRARY_DEFAULT_PORT
