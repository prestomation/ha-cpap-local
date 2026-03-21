"""DataUpdateCoordinator for CPAP Local integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
            # TODO: Switch to reader.get_all_data() once pycpap>=0.2.0 is released
            # Currently calls get_sessions() and get_device_info() separately (two fetches)
            sessions = await reader.get_sessions(since=yesterday)
            device_info = await reader.get_device_info()
        except asyncio.TimeoutError as exc:
            _LOGGER.warning("CPAP data fetch timed out")
            raise UpdateFailed("Timed out fetching CPAP data") from exc
        except OSError as exc:
            _LOGGER.warning("CPAP data fetch I/O error: %s", exc)
            raise UpdateFailed(f"I/O error fetching CPAP data: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 — last-resort catch for unexpected errors
            _LOGGER.debug("Unexpected error fetching CPAP data: %s", exc, exc_info=True)
            raise UpdateFailed(f"Unexpected error fetching CPAP data: {exc}") from exc

        latest_session = sessions[-1] if sessions else None

        # Start with existing cached data so we can fall back to it if needed
        data: dict = {
            "last_successful_sync": dt_util.now().isoformat(),
            "device": {
                "model": device_info.model,
                "serial": device_info.serial,
                "firmware": device_info.firmware,
            }
            if device_info
            else None,
        }

        if latest_session:
            def _to_utc_iso(dt: datetime) -> str:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                return dt_util.as_utc(dt).isoformat()

            # New session fetched — update last_sync
            data["last_sync"] = dt_util.now().isoformat()
            data["session"] = {
                "date": latest_session.date.isoformat(),
                "session_start": _to_utc_iso(latest_session.session_start),
                "session_end": _to_utc_iso(latest_session.session_end),
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
            # last_sync is NOT updated here — no new device data was fetched
            data["session"] = self.data["session"]
            if "last_sync" in self.data:
                data["last_sync"] = self.data["last_sync"]
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
