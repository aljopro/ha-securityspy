"""Constants shared across the SecuritySpy integration.

Anything that is a *fact about SecuritySpy* belongs to ``aiosecurityspy`` and is
re-exported here rather than restated (AD-2). Only Home Assistant-side names --
the domain -- originate in this module.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from aiosecurityspy import DEFAULT_PORT as _LIBRARY_DEFAULT_PORT

#: Integration domain. Must match the directory name and ``manifest.json``.
DOMAIN: Final = "securityspy"

#: SecuritySpy's default web-server port, taken from the library so the config
#: flow's default cannot drift from what the client actually uses.
DEFAULT_PORT: Final[int] = _LIBRARY_DEFAULT_PORT

#: How often the coordinator re-fetches `async_get_server_info()` to reconcile
#: the device registry (camera renames, additions, removals) without a manual
#: reload. There is no push stream yet (that is Epic 3), so this polling
#: timer is the only mechanism that can satisfy that requirement today; it
#: reuses AD-10's own stated 10-minute fallback-reconciliation cadence for
#: consistency, even though AD-10 is scoped to Observation Records rather than
#: device inventory. A stand-in: Epic 3's `reconnected` callback and AD-10's
#: real reconciliation cycle will likely subsume or replace this timer.
RECONCILE_INTERVAL: Final[timedelta] = timedelta(minutes=10)
