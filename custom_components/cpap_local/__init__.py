"""CPAP Local integration for Home Assistant."""
from __future__ import annotations

import hmac
import logging
from http import HTTPStatus

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_CPAP_ID,
    CONF_ESP_DEVICE_ID,
    CONF_ESP_INGEST_TOKEN,
    CONF_FETCH_METHOD,
    CONF_FETCH_METHOD_ESP,
    CONF_HTTP_URL,
    DOMAIN,
    FETCH_METHOD_HTTP,
    SCOPE_SUMMARY_ONLY,
)
from .coordinator import CPAPDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]

# Registered once per HA start, shared across all CPAP entries
_INGEST_VIEW_REGISTERED = False


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the ingest HTTP view and domain-level services once."""
    global _INGEST_VIEW_REGISTERED
    if not _INGEST_VIEW_REGISTERED:
        hass.http.register_view(CPAPIngestView())
        _INGEST_VIEW_REGISTERED = True
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CPAP Local from a config entry."""
    coordinator = CPAPDataCoordinator(hass, entry)
    await coordinator.async_setup()

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # First refresh may fail before any data has been delivered (ESP mode)
        pass

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Build cpap_id → entry_id reverse-lookup so the ingest view can route
    cpap_id = entry.data.get(CONF_CPAP_ID)
    if cpap_id:
        hass.data[DOMAIN].setdefault("_cpap_index", {})[cpap_id] = entry.entry_id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: CPAPDataCoordinator | None = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.async_shutdown()

    # Remove from cpap_id index
    cpap_id = entry.data.get(CONF_CPAP_ID)
    if cpap_id:
        hass.data[DOMAIN].get("_cpap_index", {}).pop(cpap_id, None)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


# ---------------------------------------------------------------------------
# Ingest HTTP endpoint — receives EDF bytes from an ESP WiFi bridge
# ---------------------------------------------------------------------------

class CPAPIngestView(HomeAssistantView):
    """POST /api/cpap_local/ingest/<cpap_id>

    Receives raw STR.EDF bytes from an ESPHome WiFi-bridge device after it
    has connected to the EZShare WiFi SD card adapter and downloaded the file.

    Authentication uses a per-entry bearer token configured at setup time and
    stored in the ESP's firmware (via the ESPHome secrets mechanism).

    Request headers:
        Authorization: Bearer <token>
        X-CPAP-Scope: summary_only | last_7_days | all_available  (optional)

    Request body: raw STR.EDF bytes (Content-Type: application/octet-stream)

    Response (200): {"status": "ok", "sessions_found": N, "ahi": X.X}
    Response (401): {"status": "error", "message": "..."}
    Response (404): {"status": "error", "message": "cpap_id not found"}
    """

    url = "/api/cpap_local/ingest/{cpap_id}"
    name = "api:cpap_local:ingest"
    requires_auth = False  # Uses our own per-device bearer token

    async def post(self, request: web.Request, cpap_id: str) -> web.Response:
        """Handle incoming EDF bytes from an ESP WiFi bridge."""
        hass: HomeAssistant = request.app["hass"]

        # Route to the correct coordinator by cpap_id
        cpap_index: dict = hass.data.get(DOMAIN, {}).get("_cpap_index", {})
        entry_id = cpap_index.get(cpap_id)
        if not entry_id:
            _LOGGER.warning("CPAP ingest: unknown cpap_id '%s'", cpap_id)
            return self.json(
                {"status": "error", "message": f"cpap_id '{cpap_id}' not found"},
                status_code=HTTPStatus.NOT_FOUND,
            )

        coordinator: CPAPDataCoordinator = hass.data[DOMAIN].get(entry_id)
        if not coordinator:
            return self.json(
                {"status": "error", "message": "coordinator not loaded"},
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )

        # Validate bearer token (constant-time compare to prevent timing attacks)
        expected_token = coordinator.ingest_token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or not hmac.compare_digest(
            auth_header[len("Bearer "):], expected_token or ""
        ):
            _LOGGER.warning("CPAP ingest: invalid token for cpap_id '%s'", cpap_id)
            return self.json(
                {"status": "error", "message": "Unauthorized"},
                status_code=HTTPStatus.UNAUTHORIZED,
            )

        scope = request.headers.get("X-CPAP-Scope", SCOPE_SUMMARY_ONLY)
        edf_bytes = await request.read()

        if not edf_bytes:
            return self.json(
                {"status": "error", "message": "Empty request body"},
                status_code=HTTPStatus.BAD_REQUEST,
            )

        try:
            result = await coordinator.async_ingest(edf_bytes, scope)
        except Exception as exc:
            _LOGGER.error("CPAP ingest failed for '%s': %s", cpap_id, exc)
            return self.json(
                {"status": "error", "message": str(exc)},
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

        return self.json({"status": "ok", **result})


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

def _register_services(hass: HomeAssistant) -> None:
    """Register fetch_esp and fetch_http services."""

    async def _fetch_esp(service: ServiceCall) -> None:
        """Trigger an ESPHome device to fetch CPAP data via WiFi bridge.

        Calls a native ESPHome service (<device_name>_fetch_cpap_data) on the
        configured ESP device. The ESP firmware is responsible for the WiFi
        switch sequence and POSTing data back via the ingest endpoint.
        """
        esp_device_id: str | None = service.data.get(CONF_ESP_DEVICE_ID)
        cpap_id: str | None = service.data.get(CONF_CPAP_ID)
        scope: str = service.data.get("scope", SCOPE_SUMMARY_ONLY)

        if not esp_device_id:
            _LOGGER.error("cpap_local.fetch_esp: esp_device_id is required")
            return

        dev_reg = dr.async_get(hass)
        esp_device = dev_reg.async_get(esp_device_id)
        if not esp_device:
            _LOGGER.error(
                "cpap_local.fetch_esp: device '%s' not found in device registry",
                esp_device_id,
            )
            return

        # ESPHome exposes services as: esphome.<device_slug>_<service_name>
        device_slug = (esp_device.name or "").lower().replace(" ", "_").replace("-", "_")
        esphome_service = f"{device_slug}_fetch_cpap_data"

        service_data: dict = {"scope": scope}
        if cpap_id:
            service_data["cpap_id"] = cpap_id

        try:
            await hass.services.async_call(
                "esphome",
                esphome_service,
                service_data,
                blocking=True,
            )
            _LOGGER.info(
                "cpap_local.fetch_esp: triggered esphome.%s (scope=%s)",
                esphome_service,
                scope,
            )
        except Exception as exc:
            _LOGGER.error(
                "cpap_local.fetch_esp: failed to call esphome.%s: %s",
                esphome_service,
                exc,
            )

    async def _fetch_http(service: ServiceCall) -> None:
        """Fetch CPAP data directly via HTTP from a WiFi SD card adapter."""
        http_url: str | None = service.data.get("http_url")
        scope: str = service.data.get("scope", SCOPE_SUMMARY_ONLY)

        entry = _find_entry_by_http_url(hass, http_url or "")
        if not entry:
            _LOGGER.error(
                "cpap_local.fetch_http: no entry found for URL '%s'", http_url
            )
            return

        coordinator: CPAPDataCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_refresh()

    hass.services.async_register(DOMAIN, "fetch_esp", _fetch_esp)
    hass.services.async_register(DOMAIN, "fetch_http", _fetch_http)


def _find_entry_by_http_url(hass: HomeAssistant, http_url: str) -> ConfigEntry | None:
    """Find a CPAP Local config entry matching the given http_url."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (
            entry.data.get(CONF_FETCH_METHOD) == FETCH_METHOD_HTTP
            and entry.data.get(CONF_HTTP_URL, "").rstrip("/") == http_url.rstrip("/")
        ):
            return entry
    return None
