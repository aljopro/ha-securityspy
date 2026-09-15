"""Config flow for the SecuritySpy integration.

The flow is UI-only: there is no YAML path and no discovery step. It validates
the submitted connection details against the live server before an entry is
created (``test-before-configure``) and keys the entry on the server's UUID and
nothing else (AD-5), so re-adding the same server by a different address aborts
rather than producing a second entry.

Credentials are never logged, never interpolated into a message, and never
appear in a form description (AD-13).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

import voluptuous as vol
from aiosecurityspy import (
    SecuritySpyAuthError,
    SecuritySpyCertificateError,
    SecuritySpyClient,
    SecuritySpyConnectError,
    SecuritySpyError,
    SecuritySpyPermissionError,
    SecuritySpyUnsupportedVersionError,
    ServerInfo,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_CREATE_CAMERA_ENTITIES, DEFAULT_PORT, DOMAIN

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

_LOGGER: Final = logging.getLogger(__name__)

#: Library error type -> `config.error` translation key. A tuple rather than a
#: `dict` keyed by type, because matching is by `isinstance`: a future library
#: subclass inherits its parent's message instead of falling through to
#: `unknown`.
#:
#: The order is load-bearing at the top: `SecuritySpyCertificateError` is a
#: *subclass* of `SecuritySpyConnectError`, so listing it second would make the
#: certificate message unreachable and send a user with a hostname mismatch
#: hunting for a network problem they do not have.
_ERROR_KEYS: Final[tuple[tuple[type[SecuritySpyError], str], ...]] = (
    (SecuritySpyCertificateError, "invalid_certificate"),
    (SecuritySpyAuthError, "invalid_auth"),
    (SecuritySpyPermissionError, "permission_denied"),
    (SecuritySpyUnsupportedVersionError, "unsupported_version"),
    (SecuritySpyConnectError, "cannot_connect"),
)


def _error_key(err: SecuritySpyError) -> str:
    """Map a library error to the translation key that explains it.

    Args:
        err: The error the library raised.

    Returns:
        A key in the ``config.error`` block. Anything this story does not model
        becomes ``unknown``: a generic message beats a traceback and an aborted
        flow.

    """
    for error_type, key in _ERROR_KEYS:
        if isinstance(err, error_type):
            return key
    return "unknown"


STEP_USER_DATA_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="off")
        ),
        # `cv.port` bounds the value and keeps it an `int`; the library rejects a
        # float or a `bool` port outright, and a number selector would hand it one.
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
        # Off by default: SecuritySpy's web server listens on plain HTTP out of
        # the box, and the port field defaults to that listener's port.
        vol.Required(CONF_SSL, default=False): BooleanSelector(),
        # On by default. Turning verification off is a deliberate, described
        # choice, never something a user arrives at by accepting a default.
        vol.Required(CONF_VERIFY_SSL, default=True): BooleanSelector(),
    }
)


def _build_client(hass: HomeAssistant, user_input: Mapping[str, Any]) -> SecuritySpyClient:
    """Construct a client from submitted form values.

    Kept separate from the request so the caller can tell a caller-side mistake
    -- which the constructor rejects before any network call -- apart from a
    server-side failure. Catching both around one ``await`` would report a
    decoding bug as a bad hostname.

    Args:
        hass: The Home Assistant instance, used only for its shared session.
        user_input: The submitted form values.

    Raises:
        ValueError: The host, port or credential is unusable.
        TypeError: The port is not an integer.

    Returns:
        A client bound to the described server.

    """
    verify_ssl: bool = user_input[CONF_VERIFY_SSL]
    return SecuritySpyClient(
        # inject-websession (Platinum): the config flow never builds a session.
        # Home Assistant keeps one session per verification setting, each with a
        # connector whose SSL context was built off the event loop; asking for
        # the matching one is what keeps this flow from building its own.
        async_get_clientsession(hass, verify_ssl=verify_ssl),
        user_input[CONF_HOST],
        user_input[CONF_PORT],
        username=user_input[CONF_USERNAME],
        password=user_input[CONF_PASSWORD],
        use_https=user_input[CONF_SSL],
        # Passed as well as selected: the library sends the flag as aiohttp's
        # per-request `ssl=`, and `ssl=True` resolves by deferring to the
        # connector above, so the two must agree or a request would carry a
        # verification setting the session was not built for.
        verify_ssl=verify_ssl,
    )


def _preserved_values(user_input: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return the values worth re-showing after a recoverable error.

    Everything the user typed is preserved except the password: a suggested
    value is sent back to the browser in the flow result, and a credential that
    need not make that round trip should not (AD-13). Retyping one field is a
    smaller cost than a password echoed on every failed attempt.

    Args:
        user_input: The submitted form values, or ``None`` on first display.

    Returns:
        The values to suggest in the redisplayed form.

    """
    if user_input is None:
        return {}
    return {key: value for key, value in user_input.items() if key != CONF_PASSWORD}


#: Reauth asks only for the account. Host, port and the TLS toggles stay as the
#: entry has them: changing where the server is belongs to reconfigure.
STEP_REAUTH_DATA_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
)


OPTIONS_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_CREATE_CAMERA_ENTITIES, default=True): BooleanSelector(),
    }
)


class SecuritySpyOptionsFlow(OptionsFlowWithReload):
    """Handle the tuning options for a SecuritySpy entry.

    `OptionsFlowWithReload` reloads the entry when the options change. That is
    load-bearing for live video: relay addresses cannot be revoked one by one,
    so only stopping the relay -- which the reload does -- stops them working.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options form, or save the submitted options.

        Args:
            user_input: The submitted form values, or ``None`` on first display.

        Returns:
            The form, prefilled with the current options, or the saved options.

        """
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )


class SecuritySpyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SecuritySpy."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SecuritySpyOptionsFlow:  # noqa: ARG004 - required signature
        """Return the options flow for an entry.

        Args:
            config_entry: The entry whose options are edited.

        Returns:
            A new options flow.

        """
        return SecuritySpyOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step, where the user describes their server.

        Args:
            user_input: The submitted form values, or ``None`` on first display.

        Returns:
            The created entry, an abort, or the form again with an error. A
            recoverable failure always redisplays the form with the submitted
            values intact rather than aborting the flow.

        """
        errors: dict[str, str] = {}
        if user_input is not None:
            outcome = await self._async_probe(user_input)
            if isinstance(outcome, str):
                errors["base"] = outcome
            else:
                await self.async_set_unique_id(outcome.uuid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=outcome.name, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, _preserved_values(user_input)
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],  # noqa: ARG002 - required signature
    ) -> ConfigFlowResult:
        """Start reauth after the stored credentials stopped working.

        Args:
            entry_data: The entry's stored data. Unused: the confirm step reads
                the entry itself through `_get_reauth_entry`.

        Returns:
            The confirm form.

        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the account again and update the entry in place.

        Args:
            user_input: The submitted username and password, or ``None`` on
                first display.

        Returns:
            An abort once the entry is updated (``reauth_successful``) or the
            credentials reach a different server (``wrong_server``), or the
            form again with an error.

        """
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            # Probe the server the entry already points at, with the new account.
            outcome = await self._async_probe({**entry.data, **user_input})
            if isinstance(outcome, str):
                errors["base"] = outcome
            else:
                await self.async_set_unique_id(outcome.uuid)
                # Another server's account must not quietly repoint this entry
                # and its devices, which are keyed on the original UUID.
                self._abort_if_unique_id_mismatch(reason="wrong_server")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        # Only the username is suggested, never the password -- neither the
        # stored one nor a rejected attempt (AD-13).
        username = user_input[CONF_USERNAME] if user_input else entry.data.get(CONF_USERNAME)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                STEP_REAUTH_DATA_SCHEMA, {CONF_USERNAME: username}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change where the server is reached and update the entry in place.

        Args:
            user_input: The submitted connection details, or ``None`` on first
                display.

        Returns:
            An abort once the entry is updated (``reconfigure_successful``) or
            the details reach a different server (``wrong_server``), or the form
            again with an error.

        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            outcome = await self._async_probe(user_input)
            if isinstance(outcome, str):
                errors["base"] = outcome
            else:
                await self.async_set_unique_id(outcome.uuid)
                # A new address that reaches another server must not repoint this
                # entry and its devices, which are keyed on the original UUID.
                self._abort_if_unique_id_mismatch(reason="wrong_server")
                # The title stays as the user may have renamed it; the reload
                # rebuilds the client from the new data.
                return self.async_update_reload_and_abort(entry, data_updates=user_input)

        # The stored password is never suggested, nor a rejected one (AD-13).
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA,
                _preserved_values(entry.data if user_input is None else user_input),
            ),
            errors=errors,
        )

    async def _async_probe(self, user_input: Mapping[str, Any]) -> ServerInfo | str:
        """Reach the described server, returning its info or an error key.

        Failures are returned rather than raised so the step above stays a flat
        read: every recoverable outcome redisplays the form, and none of them
        aborts the flow.

        Args:
            user_input: The submitted form values.

        Returns:
            The validated :class:`ServerInfo`, or a key in the ``config.error``
            translation block naming what went wrong.

        """
        try:
            # The constructor rejects a host carrying a scheme, port or path, and
            # a credential HTTP Basic auth cannot encode. Its messages never quote
            # the offending value, and none is shown.
            client = _build_client(self.hass, user_input)
        except TypeError, ValueError:
            return "invalid_host"

        try:
            server = await client.async_get_server_info()
        except SecuritySpyError as err:
            return _error_key(err)
        except Exception:
            # The flow must never abort on a live call. Anything the library did
            # not wrap -- a transport error it missed, a decoding bug -- would
            # otherwise escape as a traceback and end the flow. The user gets the
            # generic message and keeps their form instead.
            _LOGGER.exception("Unexpected error validating the SecuritySpy server")
            return "unknown"

        if not server.uuid:
            # Fail closed. The UUID becomes this entry's permanent identity and
            # every future device identifier (AD-5); two UUID-less servers would
            # collapse into a single entry, and inventing a fallback identity is
            # what AD-5 forbids.
            return "no_server_uuid"
        return server
