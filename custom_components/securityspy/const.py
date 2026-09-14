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

#: How often the coordinator re-fetches `async_get_camera_status()`, the cheap
#: ``++camStatus`` endpoint, to keep per-camera `last_error` current on a much
#: faster cadence than the heavy `RECONCILE_INTERVAL` poll can offer. No
#: existing constant to reuse (unlike `RECONCILE_INTERVAL`'s reuse of AD-10);
#: chosen as a reasonable "notice a stuck camera quickly" cadence for a
#: ~800B request. A tunable, not an architectural commitment -- a later story
#: may move this to options.
LIGHT_POLL_INTERVAL: Final[timedelta] = timedelta(seconds=30)

#: Options key: whether a live video `camera` entity exists per camera. On by
#: default. Turning it off reloads the entry, which stops the RTSP relay and so
#: every stream address it issued (story 2.6).
CONF_CREATE_CAMERA_ENTITIES: Final = "create_camera_entities"
