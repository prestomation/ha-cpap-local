"""CPAP Local integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import CPAPDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CPAP Local from a config entry."""
    coordinator = CPAPDataCoordinator(hass, entry)
    await coordinator.async_setup()  # loads cached data

    if coordinator.data:
        # We have cached data — load entities immediately, refresh in background
        hass.async_create_task(coordinator.async_refresh())
    else:
        # No cached data at all — must succeed on first refresh to have any state
        await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Register the sync_now service globally once (shared across all entries).
    # The handler looks up the correct coordinator for the calling entry, or
    # refreshes all coordinators when no entry_id is specified.
    if not hass.services.has_service(DOMAIN, "sync_now"):

        async def _handle_sync_now(call: ServiceCall) -> None:
            entry_id = call.data.get("entry_id")
            coordinators: dict[str, CPAPDataCoordinator] = hass.data.get(DOMAIN, {})
            if entry_id:
                coordinator = coordinators.get(entry_id)
                if coordinator:
                    await coordinator.async_refresh()
                else:
                    _LOGGER.warning("sync_now: unknown entry_id %s", entry_id)
            else:
                # Refresh all active CPAP entries
                await asyncio.gather(
                    *(c.async_refresh() for c in coordinators.values()),
                    return_exceptions=True,
                )

        hass.services.async_register(DOMAIN, "sync_now", _handle_sync_now)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: CPAPDataCoordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    # Remove the shared service only when no entries remain
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, "sync_now")

    return unload_ok
