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
    CONF_CPAP_ID,
    CONF_ESP_DEVICE_ID,
    CONF_ESP_INGEST_TOKEN,
    CONF_FETCH_METHOD,
    CONF_HTTP_URL,
    CONF_LOCAL_PATH,
    CONF_MIN_USAGE_HOURS,
    CONF_SYNC_HOUR,
    DEFAULT_AHI_THRESHOLD,
    DEFAULT_MIN_USAGE_HOURS,
    DOMAIN,
    FETCH_METHOD_HTTP,
    FETCH_METHOD_LOCAL,
    SCOPE_SUMMARY_ONLY,
    CONF_FETCH_METHOD_ESP,
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

        sync_hour = self.config_entry.data.get(CONF_SYNC_HOUR, 10)
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
        """Fetch latest CPAP session data (HTTP/local modes)."""
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
            data["session"] = self._session_to_dict(latest_session)
        elif self.data and "session" in self.data:
            data["session"] = self.data["session"]
            _LOGGER.debug("CPAP Local: no new session today, using cached data")

        await self._store.async_save(data)
        return data

    async def async_ingest(self, edf_bytes: bytes, scope: str = SCOPE_SUMMARY_ONLY) -> dict:
        """Ingest EDF bytes delivered by an ESP WiFi bridge.

        Parses the EDF data directly, updates the cached session, and fires
        a coordinator refresh so all sensors update immediately.

        Args:
            edf_bytes: Raw bytes of the STR.EDF file.
            scope: FetchScope string used for filtering.

        Returns:
            A summary dict with sessions_found and ahi.
        """
        try:
            from pycpap import ResMedReader

            since = None
            if scope == SCOPE_SUMMARY_ONLY:
                since = date.today() - timedelta(days=1)
            elif scope == "last_7_days":
                since = date.today() - timedelta(days=7)
            # "all_available" → since=None (no filter)

            sessions, _ = ResMedReader.from_bytes(edf_bytes, since=since)
        except Exception as exc:
            _LOGGER.error("CPAP ingest parse failed: %s", exc)
            raise UpdateFailed(f"STR.EDF parse failed: {exc}") from exc

        latest_session = sessions[-1] if sessions else None

        data: dict = {
            "last_sync": datetime.now().isoformat(),
            "last_ingest": True,
        }

        if latest_session:
            data["session"] = self._session_to_dict(latest_session)

        # Preserve existing device info from prior HTTP/local fetch if any
        if self.data and "device" in self.data:
            data["device"] = self.data["device"]

        await self._store.async_save(data)
        self.data = data
        self.async_update_listeners()

        ahi = latest_session.ahi if latest_session else None
        _LOGGER.info("CPAP ingest: %d session(s) parsed, latest AHI=%.1f", len(sessions), ahi or 0)

        return {
            "sessions_found": len(sessions),
            "ahi": ahi,
        }

    @staticmethod
    def _session_to_dict(session) -> dict:
        """Convert a SleepSession to a dict suitable for coordinator data."""
        return {
            "date": session.date.isoformat(),
            "session_start": session.session_start.isoformat(),
            "session_end": session.session_end.isoformat(),
            "duration_minutes": session.duration_minutes,
            "ahi": session.ahi,
            "apnea_index": session.apnea_index,
            "hypopnea_index": session.hypopnea_index,
            "mask_leak_median": session.mask_leak_median,
            "mask_leak_95": session.mask_leak_95,
            "pressure_median": session.pressure_median,
            "pressure_95": session.pressure_95,
            "mode": session.mode,
        }

    @property
    def ahi_threshold(self) -> float:
        return self.config_entry.options.get(CONF_AHI_THRESHOLD, DEFAULT_AHI_THRESHOLD)

    @property
    def min_usage_hours(self) -> float:
        return self.config_entry.options.get(CONF_MIN_USAGE_HOURS, DEFAULT_MIN_USAGE_HOURS)

    @property
    def cpap_id(self) -> str | None:
        return self.config_entry.data.get(CONF_CPAP_ID)

    @property
    def ingest_token(self) -> str | None:
        return self.config_entry.data.get(CONF_ESP_INGEST_TOKEN)
