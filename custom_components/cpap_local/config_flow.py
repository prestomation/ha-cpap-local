"""Config flow for CPAP Local integration."""
from __future__ import annotations

import logging
from pathlib import Path

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

from .const import (
    CONF_AHI_THRESHOLD,
    CONF_FETCH_METHOD,
    CONF_HTTP_URL,
    CONF_LOCAL_PATH,
    CONF_MIN_USAGE_HOURS,
    CONF_RAW_SYNC_ENABLED,
    CONF_RAW_SYNC_PATH,
    CONF_RAW_SYNC_SCOPE,
    CONF_SYNC_HOUR,
    DEFAULT_AHI_THRESHOLD,
    DEFAULT_MIN_USAGE_HOURS,
    DEFAULT_SCAN_INTERVAL_HOUR,
    DOMAIN,
    FETCH_METHOD_HTTP,
    FETCH_METHOD_LOCAL,
)

STEP_METHOD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FETCH_METHOD, default=FETCH_METHOD_HTTP): vol.In(
            [FETCH_METHOD_HTTP, FETCH_METHOD_LOCAL]
        ),
    }
)

STEP_HTTP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HTTP_URL, default="http://192.168.4.1"): str,
        vol.Optional(CONF_SYNC_HOUR, default=DEFAULT_SCAN_INTERVAL_HOUR): vol.All(
            int, vol.Range(min=0, max=23)
        ),
    }
)

STEP_LOCAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOCAL_PATH): str,
        vol.Optional(CONF_SYNC_HOUR, default=DEFAULT_SCAN_INTERVAL_HOUR): vol.All(
            int, vol.Range(min=0, max=23)
        ),
    }
)


class CPAPLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the CPAP Local config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._fetch_method: str | None = None
        # Track which URL the "cannot connect" warning was already shown for.
        # Using the URL (not just a bool) ensures that if the user changes the
        # URL after the first failure, the new URL is still validated rather than
        # being silently accepted because a warning was shown for a different URL.
        self._warned_url: str | None = None

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Step 1: Choose fetch method."""
        if user_input is not None:
            self._fetch_method = user_input[CONF_FETCH_METHOD]
            if self._fetch_method == FETCH_METHOD_HTTP:
                return await self.async_step_http()
            return await self.async_step_local()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_METHOD_SCHEMA,
        )

    async def async_step_http(self, user_input: dict | None = None) -> FlowResult:
        """Step 2a: Configure HTTP fetch."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_HTTP_URL].rstrip("/")
            connection_ok = False
            try:
                session = async_get_clientsession(self.hass)
                async with session.get(
                    f"{url}/dir?dir=A:",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    connection_ok = resp.status < 400
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("CPAP connection check failed for %s: %s", url, exc)
                connection_ok = False

            if not connection_ok and self._warned_url != url:
                # First failure for this URL: warn and allow user to proceed by
                # re-submitting the same URL.  If the user changes the URL we
                # reset and re-validate the new one.
                self._warned_url = url
                errors["base"] = "cannot_connect"
            else:
                # Either connected OK, or user re-submitted the same URL after
                # acknowledging the cannot_connect warning.
                return self.async_create_entry(
                    title=f"CPAP ({url})",
                    data={
                        CONF_FETCH_METHOD: FETCH_METHOD_HTTP,
                        CONF_HTTP_URL: url,
                        CONF_SYNC_HOUR: user_input.get(CONF_SYNC_HOUR, DEFAULT_SCAN_INTERVAL_HOUR),
                    },
                )

        return self.async_show_form(
            step_id="http",
            data_schema=STEP_HTTP_SCHEMA,
            errors=errors,
        )

    async def async_step_local(self, user_input: dict | None = None) -> FlowResult:
        """Step 2b: Configure local path fetch."""
        errors: dict[str, str] = {}

        if user_input is not None:
            path = Path(user_input[CONF_LOCAL_PATH])
            if not path.exists() or not path.is_dir():
                errors[CONF_LOCAL_PATH] = "invalid_path"
            else:
                return self.async_create_entry(
                    title=f"CPAP (local: {path})",
                    data={
                        CONF_FETCH_METHOD: FETCH_METHOD_LOCAL,
                        CONF_LOCAL_PATH: str(path),
                        CONF_SYNC_HOUR: user_input.get(CONF_SYNC_HOUR, DEFAULT_SCAN_INTERVAL_HOUR),
                    },
                )

        return self.async_show_form(
            step_id="local",
            data_schema=STEP_LOCAL_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "CPAPLocalOptionsFlow":
        return CPAPLocalOptionsFlow(config_entry)


class CPAPLocalOptionsFlow(config_entries.OptionsFlow):
    """Handle CPAP Local options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Options step: AHI threshold, min usage hours, raw sync settings."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_AHI_THRESHOLD,
                    default=current.get(CONF_AHI_THRESHOLD, DEFAULT_AHI_THRESHOLD),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_MIN_USAGE_HOURS,
                    default=current.get(CONF_MIN_USAGE_HOURS, DEFAULT_MIN_USAGE_HOURS),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_RAW_SYNC_ENABLED,
                    default=current.get(CONF_RAW_SYNC_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_RAW_SYNC_PATH,
                    default=current.get(CONF_RAW_SYNC_PATH, ""),
                ): str,
                vol.Optional(
                    CONF_RAW_SYNC_SCOPE,
                    default=current.get(CONF_RAW_SYNC_SCOPE, "last_7_days"),
                ): vol.In(["summary_only", "last_7_days", "all_available"]),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
