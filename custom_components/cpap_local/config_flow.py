"""Config flow for CPAP Local integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_AHI_THRESHOLD,
    CONF_CPAP_ID,
    CONF_ESP_DEVICE_ID,
    CONF_ESP_INGEST_TOKEN,
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
    SCOPE_ALL_AVAILABLE,
    SCOPE_LAST_7_DAYS,
    SCOPE_SUMMARY_ONLY,
    CONF_FETCH_METHOD_ESP,
    generate_ingest_token,
)


STEP_METHOD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FETCH_METHOD, default=FETCH_METHOD_HTTP): vol.In(
            [FETCH_METHOD_HTTP, FETCH_METHOD_LOCAL, CONF_FETCH_METHOD_ESP]
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

STEP_ESP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ESP_DEVICE_ID): selector.DeviceSelector(
            {
                "integration": "esphome",
            }
        ),
        vol.Required(CONF_CPAP_ID): str,
        vol.Optional(CONF_SYNC_HOUR, default=DEFAULT_SCAN_INTERVAL_HOUR): vol.All(
            int, vol.Range(min=0, max=23)
        ),
    }
)


class CPAPLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the CPAP Local config flow."""

    VERSION = 2  # Bumped for new ESP mode

    def __init__(self) -> None:
        self._fetch_method: str | None = None

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Step 1: Choose fetch method."""
        if user_input is not None:
            self._fetch_method = user_input[CONF_FETCH_METHOD]
            if self._fetch_method == FETCH_METHOD_HTTP:
                return await self.async_step_http()
            if self._fetch_method == CONF_FETCH_METHOD_ESP:
                return await self.async_step_esp()
            return await self.async_step_local()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_METHOD_SCHEMA,
        )

    async def async_step_http(self, user_input: dict | None = None) -> FlowResult:
        """Step 2a: Configure HTTP fetch."""
        if user_input is not None:
            url = user_input[CONF_HTTP_URL].rstrip("/")
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
        )

    async def async_step_local(self, user_input: dict | None = None) -> FlowResult:
        """Step 2b: Configure local path fetch."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"CPAP (local: {user_input[CONF_LOCAL_PATH]})",
                data={
                    CONF_FETCH_METHOD: FETCH_METHOD_LOCAL,
                    CONF_LOCAL_PATH: user_input[CONF_LOCAL_PATH],
                    CONF_SYNC_HOUR: user_input.get(CONF_SYNC_HOUR, DEFAULT_SCAN_INTERVAL_HOUR),
                },
            )

        return self.async_show_form(
            step_id="local",
            data_schema=STEP_LOCAL_SCHEMA,
        )

    async def async_step_esp(self, user_input: dict | None = None) -> FlowResult:
        """Step 2c: Configure ESP WiFi-bridge fetch."""
        if user_input is not None:
            cpap_id = user_input[CONF_CPAP_ID].strip()
            esp_device_id = user_input[CONF_ESP_DEVICE_ID]
            ingest_token = generate_ingest_token()
            return self.async_create_entry(
                title=f"CPAP ({cpap_id})",
                data={
                    CONF_FETCH_METHOD: CONF_FETCH_METHOD_ESP,
                    CONF_ESP_DEVICE_ID: esp_device_id,
                    CONF_CPAP_ID: cpap_id,
                    CONF_ESP_INGEST_TOKEN: ingest_token,
                    CONF_SYNC_HOUR: user_input.get(CONF_SYNC_HOUR, DEFAULT_SCAN_INTERVAL_HOUR),
                },
            )

        return self.async_show_form(
            step_id="esp",
            data_schema=STEP_ESP_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "CPAPLocalOptionsFlow":
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
                    default=current.get(CONF_RAW_SYNC_SCOPE, SCOPE_SUMMARY_ONLY),
                ): vol.In([SCOPE_SUMMARY_ONLY, SCOPE_LAST_7_DAYS, SCOPE_ALL_AVAILABLE]),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
