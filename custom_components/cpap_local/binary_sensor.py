"""Binary sensor platform for CPAP Local integration."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CPAPDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CPAP binary sensors."""
    coordinator: CPAPDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            CPAPUsedLastNightSensor(coordinator, entry),
            CPAPAHIElevatedSensor(coordinator, entry),
            CPAPCompliantSensor(coordinator, entry),
        ]
    )


def _device_info(coordinator: CPAPDataCoordinator, entry: ConfigEntry) -> DeviceInfo:
    device_data = coordinator.data.get("device") if coordinator.data else None
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="CPAP Device",
        manufacturer="ResMed",
        model=device_data["model"] if device_data else None,
    )


class CPAPUsedLastNightSensor(CoordinatorEntity, BinarySensorEntity):
    """True if CPAP was used last night (usage >= 1 hour)."""

    def __init__(self, coordinator: CPAPDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = "CPAP Used Last Night"
        self._attr_unique_id = f"{entry.entry_id}_used_last_night"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self.coordinator, self._entry)

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        session = self.coordinator.data.get("session")
        if not session:
            return False
        duration_minutes = session.get("duration_minutes", 0)
        return (duration_minutes / 60.0) >= 1.0


class CPAPAHIElevatedSensor(CoordinatorEntity, BinarySensorEntity):
    """True if last night's AHI exceeded the configured threshold."""

    def __init__(self, coordinator: CPAPDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = "CPAP AHI Elevated"
        self._attr_unique_id = f"{entry.entry_id}_ahi_elevated"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self.coordinator, self._entry)

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        session = self.coordinator.data.get("session")
        if not session:
            return None
        ahi = session.get("ahi")
        if ahi is None:
            return None
        return float(ahi) > self.coordinator.ahi_threshold


class CPAPCompliantSensor(CoordinatorEntity, BinarySensorEntity):
    """True if usage hours met the configured minimum (default 4h for insurance compliance)."""

    def __init__(self, coordinator: CPAPDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = "CPAP Compliant"
        self._attr_unique_id = f"{entry.entry_id}_compliant"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self.coordinator, self._entry)

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        session = self.coordinator.data.get("session")
        if not session:
            return False
        duration_minutes = session.get("duration_minutes", 0)
        usage_hours = duration_minutes / 60.0
        return usage_hours >= self.coordinator.min_usage_hours
