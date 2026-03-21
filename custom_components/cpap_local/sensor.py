"""Sensor platform for CPAP Local integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
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
    """Set up CPAP sensors."""
    coordinator: CPAPDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            CPAPSensor(coordinator, entry, "ahi", "AHI", "events/h", SensorStateClass.MEASUREMENT),
            CPAPSensor(coordinator, entry, "usage_hours", "Usage Hours", "h", SensorStateClass.MEASUREMENT),
            CPAPSensor(coordinator, entry, "mask_leak", "Mask Leak (Median)", "L/min", SensorStateClass.MEASUREMENT),
            CPAPSensor(coordinator, entry, "mask_leak_95", "Mask Leak (95th)", "L/min", SensorStateClass.MEASUREMENT),
            CPAPSensor(coordinator, entry, "pressure_median", "Pressure (Median)", "cmH2O", SensorStateClass.MEASUREMENT),
            CPAPSensor(coordinator, entry, "pressure_95", "Pressure (95th)", "cmH2O", SensorStateClass.MEASUREMENT),
            CPAPTimestampSensor(coordinator, entry, "session_start", "Session Start"),
            CPAPTimestampSensor(coordinator, entry, "session_end", "Session End"),
            CPAPModeSensor(coordinator, entry),
            CPAPLastSyncSensor(coordinator, entry),
        ]
    )


def _device_info(coordinator: CPAPDataCoordinator, entry: ConfigEntry) -> DeviceInfo:
    device_data = coordinator.data.get("device") if coordinator.data else None
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="CPAP Device",
        manufacturer="ResMed",
        model=device_data["model"] if device_data else None,
        sw_version=device_data["firmware"] if device_data else None,
    )


class CPAPSensor(CoordinatorEntity, SensorEntity):
    """Numeric CPAP sensor."""

    def __init__(
        self,
        coordinator: CPAPDataCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        unit: str,
        state_class: SensorStateClass,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"CPAP {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self.coordinator, self._entry)

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        session = self.coordinator.data.get("session")
        if not session:
            return None

        mapping = {
            "ahi": "ahi",
            "usage_hours": None,  # derived
            "mask_leak": "mask_leak_median",
            "mask_leak_95": "mask_leak_95",
            "pressure_median": "pressure_median",
            "pressure_95": "pressure_95",
        }

        if self._key == "usage_hours":
            duration = session.get("duration_minutes")
            return round(duration / 60.0, 2) if duration is not None else None

        field = mapping.get(self._key, self._key)
        return session.get(field)


class CPAPTimestampSensor(CoordinatorEntity, SensorEntity):
    """Timestamp CPAP sensor."""

    def __init__(
        self,
        coordinator: CPAPDataCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"CPAP {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self.coordinator, self._entry)

    @property
    def native_value(self) -> datetime | None:
        if not self.coordinator.data:
            return None
        session = self.coordinator.data.get("session")
        if not session:
            return None
        val = session.get(self._key)
        if val is None:
            return None
        try:
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            return None


class CPAPModeSensor(CoordinatorEntity, SensorEntity):
    """Therapy mode sensor."""

    def __init__(self, coordinator: CPAPDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = "CPAP Mode"
        self._attr_unique_id = f"{entry.entry_id}_mode"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self.coordinator, self._entry)

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        session = self.coordinator.data.get("session")
        return session.get("mode") if session else None


class CPAPLastSyncSensor(CoordinatorEntity, SensorEntity):
    """Timestamp of the last successful sync."""

    def __init__(self, coordinator: CPAPDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = "CPAP Last Sync"
        self._attr_unique_id = f"{entry.entry_id}_last_sync"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return _device_info(self.coordinator, self._entry)

    @property
    def native_value(self) -> datetime | None:
        if not self.coordinator.data:
            return None
        val = self.coordinator.data.get("last_sync")
        if val is None:
            return None
        try:
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            return None
