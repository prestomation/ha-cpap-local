"""DataUpdateCoordinator for CPAP Local integration."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AHI_THRESHOLD,
    CONF_FETCH_METHOD,
    CONF_HTTP_URL,
    CONF_LOCAL_PATH,
    CONF_MIN_USAGE_HOURS,
    CONF_SYNC_HOUR,
    DEFAULT_AHI_THRESHOLD,
    DEFAULT_MIN_USAGE_HOURS,
    DEFAULT_SCAN_INTERVAL_HOUR,
    DOMAIN,
    FETCH_METHOD_HTTP,
    FETCH_METHOD_LOCAL,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.cache"


class CPAPDataCoordinator(DataUpdateCoordinator):
    """Coordinator that fetches CPAP data daily and caches it to HA storage.

    Data is fetched once per day at the configured sync hour. The last known
    session is cached to HA storage so sensors survive restarts without
    showing Unknown.
    """

    def __init__(self, hass: HomeAssistant, config_entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # No automatic poll interval — we schedule manually via time_change
            update_interval=None,
        )
        self.config_entry = config_entry
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._unsub_time: Any | None = None

    async def async_setup(self) -> None:
        """Load cached data and schedule daily sync."""
        cached = await self._store.async_load()
        if cached:
            self.data = cached

        sync_hour = self.config_entry.data.get(CONF_SYNC_HOUR, DEFAULT_SCAN_INTERVAL_HOUR)
        self._unsub_time = async_track_time_change(
            self.hass,
            self._async_scheduled_refresh,
            hour=sync_hour,
            minute=0,
            second=0,
        )
        _LOGGER.debug("CPAP Local: scheduled daily sync at %02d:00", sync_hour)

    @callback
    def _async_scheduled_refresh(self, now: datetime) -> None:
        """Called by async_track_time_change at the configured hour."""
        self.hass.async_create_task(self.async_refresh())

    async def async_shutdown(self) -> None:
        """Cancel the scheduled time listener."""
        if self._unsub_time is not None:
            self._unsub_time()
            self._unsub_time = None

    def _build_fetcher(self):
        """Construct the appropriate pycpap fetcher from config."""
        try:
            from pycpap import HttpFetcher, LocalFetcher
        except ImportError as exc:
            raise UpdateFailed("pycpap is not installed") from exc

        method = self.config_entry.data.get(CONF_FETCH_METHOD)
        if method == FETCH_METHOD_HTTP:
            url = self.config_entry.data[CONF_HTTP_URL]
            return HttpFetcher(url)
        elif method == FETCH_METHOD_LOCAL:
            path = self.config_entry.data[CONF_LOCAL_PATH]
            return LocalFetcher(path)
        else:
            raise UpdateFailed(f"Unknown fetch method: {method}")

    async def _async_update_data(self) -> dict:
        """Fetch latest CPAP session data."""
        try:
            from pycpap import ResMedReader
        except ImportError as exc:
            raise UpdateFailed("pycpap is not installed") from exc

        fetcher = self._build_fetcher()
        reader = ResMedReader(fetcher)

        yesterday = date.today() - timedelta(days=1)

        try:
            sessions = await reader.get_sessions(since=yesterday)
            device_info = await reader.get_device_info()
        except Exception as exc:
            _LOGGER.warning("CPAP data fetch failed: %s", exc)
            raise UpdateFailed(f"Failed to fetch CPAP data: {exc}") from exc

        latest_session = sessions[-1] if sessions else None

        data: dict = {
            "last_sync": datetime.now().isoformat(),
            "device": {
                "model": device_info.model,
                "serial": device_info.serial,
                "firmware": device_info.firmware,
            }
            if device_info
            else None,
        }

        if latest_session:
            data["session"] = {
                "date": latest_session.date.isoformat(),
                "session_start": latest_session.session_start.isoformat(),
                "session_end": latest_session.session_end.isoformat(),
                "duration_minutes": latest_session.duration_minutes,
                "ahi": latest_session.ahi,
                "apnea_index": latest_session.apnea_index,
                "hypopnea_index": latest_session.hypopnea_index,
                "mask_leak_median": latest_session.mask_leak_median,
                "mask_leak_95": latest_session.mask_leak_95,
                "pressure_median": latest_session.pressure_median,
                "pressure_95": latest_session.pressure_95,
                "mode": latest_session.mode,
            }
        elif self.data and "session" in self.data:
            # Preserve last known session if today's data isn't available yet
            data["session"] = self.data["session"]
            _LOGGER.debug("CPAP Local: no new session today, using cached data")

        # Cache to persistent storage
        await self._store.async_save(data)

        return data

    @property
    def ahi_threshold(self) -> float:
        return self.config_entry.options.get(CONF_AHI_THRESHOLD, DEFAULT_AHI_THRESHOLD)

    @property
    def min_usage_hours(self) -> float:
        return self.config_entry.options.get(CONF_MIN_USAGE_HOURS, DEFAULT_MIN_USAGE_HOURS)
