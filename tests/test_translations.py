"""Translation coverage: every key the code emits must resolve to a message.

`strings.json` and `translations/en.json` are maintained as duplicates, which is
what Home Assistant expects but nothing enforces. Left to a manual check, the
first divergence surfaces as a raw key such as `unknown` in the user's browser,
with a green test suite. These tests make that a failure instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.securityspy import config_flow

COMPONENT_DIR = Path(config_flow.__file__).parent
STRINGS = COMPONENT_DIR / "strings.json"
EN_TRANSLATIONS = COMPONENT_DIR / "translations" / "en.json"


def _load(path: Path) -> dict[str, Any]:
    """Read one translation document."""
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def test_english_translations_match_strings() -> None:
    """`translations/en.json` is the served copy and must not drift from source."""
    assert _load(EN_TRANSLATIONS) == _load(STRINGS)


#: Error keys the flow returns as literals rather than through `_ERROR_KEYS`.
#: Kept short deliberately: everything mapped from a library error is derived
#: below, so adding a mapping cannot silently escape this test.
_LITERAL_ERROR_KEYS = frozenset({"invalid_host", "no_server_uuid", "unknown"})

#: Every key the user step can put in `errors["base"]`, derived from the code so
#: a new mapping with no message is a failure rather than a green suite.
FLOW_ERROR_KEYS = _LITERAL_ERROR_KEYS | {key for _, key in config_flow._ERROR_KEYS}  # noqa: SLF001


@pytest.mark.parametrize("error_key", sorted(FLOW_ERROR_KEYS))
def test_every_flow_error_has_a_message(error_key: str) -> None:
    """Each error key the user step can set resolves to a translated string."""
    assert _load(STRINGS)["config"]["error"][error_key]


def test_no_unused_error_messages() -> None:
    """The `config.error` block matches the code exactly, with nothing stranded.

    A message no code path can emit is dead weight that outlives the branch it
    described; this makes removing the branch also remove the string.
    """
    assert set(_load(STRINGS)["config"]["error"]) == FLOW_ERROR_KEYS


@pytest.mark.parametrize(
    "exception_key",
    [
        "cannot_connect",
        "invalid_auth",
        "invalid_certificate",
        "invalid_stored_data",
        "unknown",
        "unsupported_version",
    ],
)
def test_every_setup_failure_has_a_message(exception_key: str) -> None:
    """Each translation key `async_setup_entry` raises with resolves to a string."""
    assert _load(STRINGS)["exceptions"][exception_key]["message"]


def test_every_form_field_is_labelled_and_described() -> None:
    """The user step labels and explains every field it collects.

    The field set is read off the schema rather than restated: a field added to
    the form with no label would otherwise pass here and show a raw key in the
    browser, which is the drift this module exists to catch.
    """
    fields = {str(marker) for marker in config_flow.STEP_USER_DATA_SCHEMA.schema}
    user_step = _load(STRINGS)["config"]["step"]["user"]
    assert set(user_step["data"]) == fields
    assert set(user_step["data_description"]) == fields
