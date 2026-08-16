"""Shared fixtures for the SecuritySpy integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final
from unittest.mock import MagicMock, patch

import pytest
from aiosecurityspy import ServerInfo
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

if TYPE_CHECKING:
    from collections.abc import Generator

SERVER_UUID: Final = "1D3A5C7E-9B21-4F60-8A44-0C2E6F1B7D93"
SERVER_NAME: Final = "nvr"

#: The four fields the user step collects, and the only four an entry stores.
MOCK_USER_INPUT: Final[dict[str, Any]] = {
    CONF_HOST: "192.168.1.20",
    CONF_PORT: 8000,
    CONF_USERNAME: "homeassistant",
    CONF_PASSWORD: "hunter2",
}


def make_server_info(uuid: str = SERVER_UUID, name: str = SERVER_NAME) -> ServerInfo:
    """Build a ``ServerInfo`` without going near the wire."""
    return ServerInfo(
        uuid=uuid,
        name=name,
        version="6.20",
        version_info=(6, 20),
        camera_count=0,
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Load `custom_components/` in every test; required for custom integrations.

    The parameter is requested purely for its side effect: it is what makes
    Home Assistant willing to load an integration from `custom_components/`.
    """


@pytest.fixture
def mock_client_class() -> Generator[MagicMock]:
    """Patch `SecuritySpyClient` at both import sites with one shared mock.

    The config flow and `async_setup_entry` each import the class by name, so
    both bindings have to be replaced; sharing a single mock keeps a test's
    `side_effect` in force across a flow that ends by setting the entry up.
    """
    with (
        patch(
            "custom_components.securityspy.config_flow.SecuritySpyClient", autospec=True
        ) as client_class,
        patch("custom_components.securityspy.SecuritySpyClient", new=client_class),
    ):
        client_class.return_value.async_get_server_info.return_value = make_server_info()
        yield client_class


@pytest.fixture
def mock_client(mock_client_class: MagicMock) -> MagicMock:
    """Return the mocked client instance the patched class hands out."""
    instance: MagicMock = mock_client_class.return_value
    return instance
